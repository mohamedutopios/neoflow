"""Étape 4 — validation automatique : Gherkin, OpenAPI, traçabilité. Aucun modèle."""
from __future__ import annotations

from pathlib import Path

from neospec import config
from neospec.validation import gherkin, openapi, tracabilite
from neospec.validation.rapport import Rapport

__all__ = ["Rapport", "valider_tout"]


def valider_tout(racine: Path, type_: str, exiger_commits: bool = False) -> Rapport:
    racine = racine.resolve()
    rapport = Rapport()
    s = config.slug(type_)
    spec = racine / "docs" / "specs" / f"{type_}.md"
    dossier = racine / "docs" / "specs" / s
    if not spec.exists():
        rapport.erreur(f"Spécification absente : docs/specs/{type_}.md")
        return rapport
    exigences = tracabilite.verifier_spec(spec.read_text(encoding="utf-8"), rapport, f"docs/specs/{type_}.md")
    features = sorted((dossier / "features").glob("*.feature"))
    if not features:
        rapport.erreur(f"Aucun fichier .feature dans docs/specs/{s}/features")
    couverture = gherkin.valider_features(features, exigences, rapport, racine)
    matrice = dossier / "MATRICE_TRACABILITE.md"
    tracabilite.verifier_matrice(matrice.read_text(encoding="utf-8") if matrice.exists() else None,
                                 exigences, couverture, rapport)
    contrats = sorted((dossier / "openapi").glob("*.y*ml"))
    if not contrats:
        rapport.erreur(f"Aucun contrat OpenAPI dans docs/specs/{s}/openapi")
    for c in contrats:
        openapi.valider_contrat(c, exigences, rapport, str(c.relative_to(racine)))
    tracabilite.verifier_adr_et_plan(racine, type_, exigences, dossier / "PLAN_TACHES.md", rapport)
    if exiger_commits:
        tracabilite.verifier_commits(racine, exigences, rapport)
    return rapport
