"""Traçabilité : lecture de la spécification, matrice, ADR, plan et commits."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from neospec.config import ID_EXIGENCE, RE_ID_EXIGENCE, RE_ID_SEUL, STATUTS_SPEC, est_fonctionnelle
from neospec.validation.rapport import Rapport


def lire_spec(texte: str) -> tuple[str, dict[str, str], list[str], int]:
    """Renvoie (statut, {exigence: titre}, hypothèses « À valider », nombre d'hypothèses)."""
    m = re.search(r"^\|\s*Statut\s*\|\s*([^|\n]+?)\s*\|", texte, re.M)
    statut = m.group(1) if m else "(absent)"
    exigences: dict[str, str] = {}
    for m in re.finditer(rf"^#{{2,4}}\s+({ID_EXIGENCE})\b\s*[—–-]?\s*(.*)$", texte, re.M):
        exigences.setdefault(m.group(1), m.group(2).strip())
    hypotheses = re.findall(r"^\|\s*(H-\d{2,3})\s*\|(.*)$", texte, re.M)
    en_attente = [h for h, reste in hypotheses if re.search(r"[ÀA] valider", reste, re.I)]
    return statut, exigences, en_attente, len(hypotheses)


def verifier_spec(texte: str, rapport: Rapport, nom: str) -> dict[str, str]:
    statut, exigences, en_attente, nb_h = lire_spec(texte)
    doublons = [i for i in set(re.findall(rf"^#{{2,4}}\s+({ID_EXIGENCE})\b", texte, re.M))
                if len(re.findall(rf"^#{{2,4}}\s+{re.escape(i)}\b", texte, re.M)) > 1]
    for i in sorted(doublons):
        rapport.erreur(f"Exigence définie deux fois dans la spécification : {i}")
    if statut not in STATUTS_SPEC:
        rapport.avertir(f"Statut de spécification inattendu « {statut} » (attendu : {', '.join(STATUTS_SPEC)})")
    ef = [i for i in exigences if est_fonctionnelle(i)]
    if not ef:
        rapport.erreur("Aucune exigence fonctionnelle (titres « ### EF-01 — … » attendus)")
    if en_attente:
        if statut == "BROUILLON":
            rapport.info(f"{len(en_attente)} hypothèse(s) à valider (porte 1 non franchie) : {', '.join(en_attente)}")
        else:
            rapport.erreur(f"Statut « {statut} » alors que des hypothèses sont à valider : {', '.join(en_attente)}")
    rapport.info(f"Spécification {nom} : statut {statut}, {len(ef)} EF, {len(exigences) - len(ef)} ENF, {nb_h} hypothèse(s)")
    return exigences


def _cellules(ligne: str) -> list[str]:
    return [c.strip() for c in ligne.strip().strip("|").split("|")]


def _renseigne(cellule: str | None) -> bool:
    return bool(cellule) and not re.fullmatch(r"[—–-]+", cellule or "")


def verifier_matrice(texte: str | None, exigences: dict[str, str], couverture: dict[str, int], rapport: Rapport) -> None:
    """Contrôle la matrice de traçabilité contre la spécification et la couverture Gherkin.

    - matrice absente, ou en-tête « | Exigence | … Scénario(s) … | … Test(s) … » introuvable : erreur ;
    - ligne citant une exigence inconnue : erreur ; exigence absente de la matrice : erreur ;
    - EF couverte par aucun scénario : erreur ;
    - ENF sans scénario : erreur si la cellule Test(s) est vide ou « — », sinon information
      (« ENF-xx prouvée hors Gherkin : … »).
    """
    # TODO TP3 : repérer l'en-tête, lire les lignes d'exigences, croiser avec la spécification et la couverture Gherkin.
    raise NotImplementedError("TODO TP3 : verifier_matrice")


def verifier_adr_et_plan(racine: Path, type_: str, exigences: dict[str, str], plan: Path, rapport: Rapport) -> None:
    if not plan.exists():
        rapport.avertir(f"Plan de tâches absent : {plan.relative_to(racine)}")
    lies = []
    for f in sorted((racine / "docs" / "adr").glob("ADR-*.md")):
        texte = f.read_text(encoding="utf-8")
        if f"{type_}.md" in texte and any(i in exigences for i in RE_ID_EXIGENCE.findall(texte)):
            lies.append(f.name)
    if lies:
        rapport.info(f"ADR liés : {', '.join(lies)}")
    else:
        rapport.avertir(f"Aucun ADR ne cite docs/specs/{type_}.md et ses exigences")


def verifier_commits(racine: Path, exigences: dict[str, str], rapport: Rapport) -> None:
    r = subprocess.run(["git", "-C", str(racine), "log", "--format=%s%n%b"], capture_output=True, text=True)
    if r.returncode != 0:
        rapport.erreur("git log impossible : le dossier n'est pas un dépôt Git ?")
        return
    cites = set(re.findall(rf"\[({ID_EXIGENCE})\]", r.stdout))
    for i in exigences:
        if i not in cites:
            (rapport.erreur if est_fonctionnelle(i) else rapport.avertir)(
                f"{i} n'est citée dans aucun message de commit (« [{i}] » attendu)")
