"""Constantes du lab : modèles, efforts, chemins autorisés, conventions de nommage."""
from __future__ import annotations

import re
from pathlib import Path

# Modèles (choix de modèles de la formation) : planification sur Opus, rédaction sur Sonnet.
MODELES = {
    "questions": "claude-opus-5-5",
    "generation": "claude-sonnet-5-5",
    "correction": "claude-sonnet-5-5",
}
# Profondeur de raisonnement par étape (output_config.effort). Opus 5.5 vaut « medium » par défaut.
EFFORTS = {"questions": "high", "generation": "medium", "correction": "medium"}
# Sorties longues (six fichiers .feature et un contrat) : streaming obligatoire au-delà de ~16 000.
MAX_TOKENS = 64000

# Garde-fous d'écriture (J2) : l'assistant n'écrit que dans ces dossiers du dépôt.
ZONES_ECRITURE = (
    "docs/specs",
    "docs/adr",
    "backend/src/test/java",
    "backend/src/test/resources/features",
)

# Identifiants d'exigences acceptés : EF-01, CONG-EF-01 ou EF-CONGES-01 (docs/specs/README.md du socle).
ID_EXIGENCE = r"(?:[A-Z]{2,6}-)?(?:EF|ENF)(?:-[A-Z][A-Z_]{1,19})?-\d{2,3}"
RE_ID_EXIGENCE = re.compile(rf"(?<![A-Za-z0-9_-]){ID_EXIGENCE}(?![0-9])")
RE_ID_SEUL = re.compile(rf"^{ID_EXIGENCE}$")
STATUTS_SPEC = ("BROUILLON", "HYPOTHÈSES VALIDÉES", "EN REVUE", "PRÊTE")


def est_fonctionnelle(id_: str) -> bool:
    return re.search(r"(^|-)EF-", id_) is not None


def slug(type_: str) -> str:
    """CONGES → conges ; NOTE_DE_FRAIS → note-de-frais."""
    return type_.lower().replace("_", "-")


def racine_par_defaut() -> Path:
    """labs/spec/neospec/config.py → racine du dépôt NeoFlow."""
    return Path(__file__).resolve().parents[3]


def lab_dir() -> Path:
    return Path(__file__).resolve().parents[1]
