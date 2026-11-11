"""Outils de neoagent : le contrat `Tool` et les six outils de base.

Un outil renvoie du TEXTE, considéré comme une donnée non fiable : le modèle le lit, rien ne l'exécute.
Chaque outil applique la `Politique` lui-même (défense en profondeur) ; l'agent ajoute l'approbation humaine
pour les outils à risque « ecriture » et « execution ».
"""

from __future__ import annotations

import difflib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from neoagent.garde_fous import Politique, RefusGardeFou

NOM_OUTIL = re.compile(r"^[a-z0-9_]{1,64}$")


class ErreurOutil(Exception):
    """Erreur métier d'un outil (fichier absent, motif ambigu) : renvoyée au modèle, pas une panne."""


@dataclass
class Tool:
    name: str                       # ^[a-z0-9_]{1,64}$
    description: str
    input_schema: dict              # JSON Schema de l'input
    handler: Callable[[dict], str]  # renvoie du texte (données non fiables)
    risque: Literal["lecture", "ecriture", "execution"] = "lecture"
    apercu: Callable[[dict], str] | None = None  # aperçu montré à l'approbateur (diff, commande)

    def __post_init__(self) -> None:
        if not NOM_OUTIL.match(self.name):
            raise ValueError(f"nom d'outil invalide (attendu ^[a-z0-9_]{{1,64}}$) : {self.name!r}")
        if self.risque not in ("lecture", "ecriture", "execution"):
            raise ValueError(f"risque inconnu : {self.risque!r}")
        if not isinstance(self.input_schema, dict) or self.input_schema.get("type") != "object":
            raise ValueError(f"input_schema de {self.name} : objet JSON Schema attendu")

    def definition(self) -> dict:
        """Définition envoyée à l'API Claude (paramètre `tools`)."""
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


def _schema(proprietes: dict, requis: list[str]) -> dict:
    return {"type": "object", "properties": proprietes, "required": requis, "additionalProperties": False}


def _tronquer(texte: str, maximum: int) -> str:
    if len(texte) <= maximum:
        return texte
    return texte[:maximum] + f"\n… [tronqué : {len(texte) - maximum} caractères de plus]"


def _parcourir(politique: Politique, depart: Path):
    """Fichiers sous `depart`, triés, hors dossiers ignorés et chemins interdits (déterministe)."""
    for chemin in sorted(depart.rglob("*")):
        relatif = chemin.relative_to(politique.racine.resolve())
        if any(partie in politique.ignores_parcours for partie in relatif.parts):
            continue
        if chemin.is_file():
            try:
                politique.resoudre(str(relatif))
            except RefusGardeFou:
                continue
            yield chemin


def outils_de_base(repo: Path, politique: Politique) -> list[Tool]:
    """lire_fichier, chercher, lister, editer_fichier, executer_commande (allowlistée), git_diff."""
    repo = Path(repo)
    if repo.resolve() != politique.racine.resolve():
        raise ValueError(f"le dépôt {repo} doit être la racine de la politique {politique.racine}")

    def lire_fichier(entree: dict) -> str:
        cible = politique.resoudre(entree["chemin"])
        if not cible.is_file():
            raise ErreurOutil(f"fichier introuvable : {entree['chemin']}")
        lignes = cible.read_text(encoding="utf-8", errors="replace").splitlines()
        debut = max(int(entree.get("debut", 1)), 1)
        fin = min(int(entree.get("fin", len(lignes))), len(lignes))
        rendu = "\n".join(f"{n:>5}\t{lignes[n - 1]}" for n in range(debut, fin + 1))
        return _tronquer(rendu or "(fichier vide)", politique.taille_max_lecture)

    def chercher(entree: dict) -> str:
        try:
            motif = re.compile(entree["motif"])
        except re.error as exc:
            raise ErreurOutil(f"expression régulière invalide : {exc}") from exc
        depart = politique.resoudre(entree.get("chemin", "."))
        filtre = entree.get("fichiers", "*")
        maximum = int(entree.get("max_resultats", 50))
        resultats: list[str] = []
        for fichier in _parcourir(politique, depart):
            if not fichier.match(filtre):
                continue
            try:
                texte = fichier.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for numero, ligne in enumerate(texte.splitlines(), start=1):
                if motif.search(ligne):
                    resultats.append(f"{politique.relatif(fichier)}:{numero}: {ligne.strip()[:200]}")
                    if len(resultats) >= maximum:
                        return "\n".join(resultats) + f"\n… [limite de {maximum} résultats atteinte]"
        return "\n".join(resultats) if resultats else "aucun résultat"

    def lister(entree: dict) -> str:
        depart = politique.resoudre(entree.get("chemin", "."))
        if not depart.is_dir():
            raise ErreurOutil(f"dossier introuvable : {entree.get('chemin')}")
        profondeur = int(entree.get("profondeur", 2))
        lignes: list[str] = []
        for fichier in _parcourir(politique, depart):
            relatif = fichier.relative_to(depart)
            if len(relatif.parts) <= profondeur:
                lignes.append(relatif.as_posix())
        return _tronquer("\n".join(lignes) or "(vide)", politique.taille_max_sortie)

    def _nouveau_contenu(entree: dict) -> tuple[Path, str, str]:
        cible = politique.verifier_ecriture(entree["chemin"])
        ancien, nouveau = entree.get("ancien", ""), entree["nouveau"]
        if ancien == "":
            if cible.exists():
                raise ErreurOutil(f"{entree['chemin']} existe déjà : fournissez « ancien » pour le modifier")
            return cible, "", nouveau
        if not cible.is_file():
            raise ErreurOutil(f"fichier introuvable : {entree['chemin']}")
        actuel = cible.read_text(encoding="utf-8")
        occurrences = actuel.count(ancien)
        if occurrences == 0:
            raise ErreurOutil("texte « ancien » introuvable : relisez le fichier, copiez l'extrait exact")
        if occurrences > 1:
            raise ErreurOutil(f"texte « ancien » ambigu ({occurrences} occurrences) : ajoutez du contexte")
        return cible, actuel, actuel.replace(ancien, nouveau, 1)

    def apercu_edition(entree: dict) -> str:
        try:
            cible, avant, apres = _nouveau_contenu(entree)
        except (RefusGardeFou, ErreurOutil) as exc:
            return f"(édition invalide : {exc})"
        nom = politique.relatif(cible) if cible.exists() else entree["chemin"]
        return "".join(difflib.unified_diff(avant.splitlines(True), apres.splitlines(True),
                                            fromfile=f"a/{nom}", tofile=f"b/{nom}")) or "(aucun changement)"

    def editer_fichier(entree: dict) -> str:
        cible, _, apres = _nouveau_contenu(entree)
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(apres, encoding="utf-8")
        return f"écrit : {politique.relatif(cible)} ({len(apres.splitlines())} lignes)"

    def _executer(argv: list[str], cwd: Path) -> str:
        try:
            fini = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                                  timeout=politique.timeout_commande_s, env=politique.environnement())
        except subprocess.TimeoutExpired:
            raise ErreurOutil(f"délai dépassé ({politique.timeout_commande_s} s) : {' '.join(argv)}") from None
        except FileNotFoundError:
            raise ErreurOutil(f"programme introuvable : {argv[0]}") from None
        sortie = (fini.stdout + ("\n" + fini.stderr if fini.stderr else "")).strip()
        # La fin de sortie porte le diagnostic (Maven, Vitest) : on garde la queue, pas la tête.
        if len(sortie) > politique.taille_max_sortie:
            sortie = "[début tronqué]\n" + sortie[-politique.taille_max_sortie:]
        return f"code retour {fini.returncode}\n{sortie}"

    def executer_commande(entree: dict) -> str:
        argv, cwd = politique.verifier_commande(entree["commande"], entree.get("repertoire"))
        return _executer(argv, cwd)

    def git_diff(entree: dict) -> str:
        argv = ["git", "diff", "--stat"] if entree.get("stat") else ["git", "diff"]
        if entree.get("chemin"):
            argv += ["--", politique.relatif(politique.resoudre(entree["chemin"]))]
        diff = _executer(argv, politique.racine.resolve())
        non_suivis = _executer(["git", "ls-files", "--others", "--exclude-standard"], politique.racine.resolve())
        fichiers = [ligne for ligne in non_suivis.splitlines()[1:] if ligne.strip()]
        return diff + ("\nfichiers nouveaux non suivis :\n" + "\n".join(fichiers) if fichiers else "")

    return [
        Tool("lire_fichier", "Lit un fichier texte du dépôt, avec numéros de ligne. Utilisez debut/fin pour les gros fichiers.",
             _schema({"chemin": {"type": "string", "description": "chemin relatif à la racine du dépôt"},
                      "debut": {"type": "integer", "minimum": 1}, "fin": {"type": "integer", "minimum": 1}}, ["chemin"]),
             lire_fichier),
        Tool("chercher", "Cherche une expression régulière dans les fichiers du dépôt ; renvoie chemin:ligne: texte.",
             _schema({"motif": {"type": "string"}, "chemin": {"type": "string", "default": "."},
                      "fichiers": {"type": "string", "description": "motif de nom, ex. *.java", "default": "*"},
                      "max_resultats": {"type": "integer", "minimum": 1, "maximum": 200}}, ["motif"]),
             chercher),
        Tool("lister", "Liste les fichiers d'un dossier du dépôt (hors .git, node_modules, target).",
             _schema({"chemin": {"type": "string", "default": "."},
                      "profondeur": {"type": "integer", "minimum": 1, "maximum": 12}}, []),
             lister),
        Tool("editer_fichier", "Remplace un extrait exact et unique d'un fichier (ancien → nouveau), ou crée un fichier si "
             "« ancien » est vide. Relisez le fichier avant ; ne modifiez jamais un test pour le faire passer.",
             _schema({"chemin": {"type": "string"}, "ancien": {"type": "string", "default": ""},
                      "nouveau": {"type": "string"}}, ["chemin", "nouveau"]),
             editer_fichier, risque="ecriture", apercu=apercu_edition),
        Tool("executer_commande", "Exécute une commande de l'allowlist (tests, build, lint, git en lecture), sans shell. "
             "Utilisez « repertoire » (ex. backend) au lieu de cd.",
             _schema({"commande": {"type": "string", "description": "ex. ./mvnw -q test -Dtest=RegleCongesTest"},
                      "repertoire": {"type": "string", "description": "sous-dossier du dépôt, ex. backend"}}, ["commande"]),
             executer_commande, risque="execution",
             apercu=lambda e: f"$ (cd {e.get('repertoire') or '.'} && {e.get('commande')})"),
        Tool("git_diff", "Montre le diff de l'arbre de travail (ou --stat), et les fichiers nouveaux non suivis.",
             _schema({"chemin": {"type": "string"}, "stat": {"type": "boolean", "default": False}}, []),
             git_diff),
    ]
