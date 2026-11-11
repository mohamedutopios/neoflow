"""Étape 3 — décisions → spécification, scénarios Gherkin, delta OpenAPI, matrice, plan, ADR."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from neospec import config, rendu, schemas
from neospec.arbitrage import verifier_porte_1
from neospec.llm import ClientLLM
from neospec.prompts import prompt


def decisions_pour_modele(decisions: dict[str, Any]) -> dict[str, Any]:
    """Ce que le modèle doit voir : les décisions, pas les métadonnées inutiles."""
    return {
        "questions": [{k: q.get(k) for k in ("id", "question", "source", "priorite", "decision", "hypothese")}
                      for q in decisions["questions"]],
        "hypotheses": [{k: h.get(k) for k in ("id", "enonce", "statut", "valide_par")} for h in decisions["hypotheses"]],
        "termes_a_chiffrer": decisions.get("termes_a_chiffrer", []),
    }


def lire_brouillons(racine: Path, type_: str, limite: int = 20000) -> str:
    """Scénarios et contrats écrits à la main (TP 2 et 3) dans docs/specs/<type>/brouillons/."""
    dossier = racine / "docs" / "specs" / config.slug(type_) / "brouillons"
    blocs = [f"--- {f.name}\n{f.read_text(encoding='utf-8')[:limite]}"
             for f in sorted(dossier.glob("*")) if f.suffix in (".feature", ".yaml", ".yml", ".md")] if dossier.exists() else []
    return "\n".join(blocs)


def construire_message(ticket: str, type_: str, decisions: dict[str, Any], socle: str, brouillons: str = "") -> str:
    message = (
        f"Variante : {type_} (fichiers dans docs/specs/{config.slug(type_)}/, étiquette @{config.slug(type_)})\n\n"
        f"<ticket>\n{ticket}\n</ticket>\n\n"
        f"<decisions>{json.dumps(decisions_pour_modele(decisions), ensure_ascii=False)}</decisions>\n\n"
        f"<socle>\n{socle}\n</socle>\n\n"
    )
    if brouillons:
        message += f"<brouillons>\n{brouillons}\n</brouillons>\n\n"
    return message + "Produis la spécification complète au format demandé, à partir des seules hypothèses validées."


def generer(client: ClientLLM, ticket: str, type_: str, decisions: dict[str, Any], socle: str = "",
            brouillons: str = "") -> dict[str, Any]:
    """Appelle le modèle (étape « generation ») et renvoie la génération validée par le schéma local.

    La porte 1 est vérifiée AVANT l'appel : sans décision humaine sur chaque question, aucune
    génération (et aucun token dépensé). Les brouillons humains (scénarios, contrat) sont transmis
    au modèle comme entrée prioritaire. Lève arbitrage.PorteNonFranchie ou schemas.SortieInvalide.
    """
    # TODO TP fil rouge : verifier_porte_1 AVANT l'appel, client.json(etape='generation', ...) avec prompt('generation'), construire_message(...) et schemas.GENERATION_API, puis schemas.valider_json(..., GENERATION_LOCAL).
    raise NotImplementedError("TODO TP fil rouge : generer")


def statut_existant(chemin_spec: Path) -> str | None:
    if not chemin_spec.exists():
        return None
    m = re.search(r"^\|\s*Statut\s*\|\s*([^|\n]+?)\s*\|", chemin_spec.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def ecrire_artefacts(racine: Path, type_: str, decisions: dict[str, Any], g: dict[str, Any],
                     statut: str = "EN REVUE", forcer: bool = False) -> list[Path]:
    """Écrit spécification, features, contrat, matrice, plan et ADR (zones autorisées uniquement).

    Refuse d'écraser une spécification au statut PRÊTE (porte 4 humaine), sauf --forcer.
    Les anciens fichiers .feature du dossier sont remplacés par ceux de la génération.
    """
    s = config.slug(type_)
    spec = rendu.chemin_autorise(racine, Path("docs/specs") / f"{type_}.md")
    if statut_existant(spec) == "PRÊTE" and not forcer:
        raise rendu.EcritureInterdite(f"{spec} est au statut PRÊTE : seule une modification humaine est permise")
    dossier = rendu.chemin_autorise(racine, Path("docs/specs") / s)
    dossier_adr = rendu.chemin_autorise(racine, Path("docs/adr"))
    numero = rendu.prochain_numero_adr(dossier_adr, g["adr"]["slug"])
    nom_adr = f"ADR-{numero:03d}-{g['adr']['slug']}.md"
    fichiers: dict[Path, str] = {
        spec: rendu.rendre_spec(type_, decisions, g, statut=statut, adr=f"docs/adr/{nom_adr}"),
        dossier / "MATRICE_TRACABILITE.md": rendu.rendre_matrice(type_, g),
        dossier / "PLAN_TACHES.md": rendu.rendre_plan(type_, g),
        dossier / "openapi" / f"{s}-delta.yaml": g["openapi_delta"].rstrip() + "\n",
        dossier_adr / nom_adr: rendu.rendre_adr(numero, type_, str(decisions.get("date")), g),
    }
    for f in g["features"]:
        fichiers[rendu.chemin_autorise(racine, dossier / "features" / f["fichier"])] = f["contenu"].rstrip() + "\n"
    anciens = dossier / "features"
    if anciens.exists():
        for vieux in anciens.glob("*.feature"):
            if vieux not in fichiers:
                vieux.unlink()
    for chemin, contenu in fichiers.items():
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
    return sorted(fichiers)
