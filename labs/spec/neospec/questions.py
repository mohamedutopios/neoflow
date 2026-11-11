"""Étape 1 — ticket → questions, hypothèses, contradictions, risques (sortie JSON Schema)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from neospec import schemas
from neospec.llm import ClientLLM
from neospec.prompts import prompt

FICHIERS_SOCLE = (
    "backend/src/main/java/com/neosoft/neoflow/regles/RegleMetierDemande.java",
    "backend/src/main/java/com/neosoft/neoflow/demande/StatutDemande.java",
    "backend/src/main/java/com/neosoft/neoflow/demande/dto/DemandeRequest.java",
    "backend/src/main/java/com/neosoft/neoflow/common/GlobalExceptionHandler.java",
)


def lire_contexte_socle(racine: Path, limite: int = 4000) -> str:
    """Extraits du socle utiles pour repérer les contradictions entre ticket et code."""
    blocs = []
    for rel in FICHIERS_SOCLE:
        chemin = racine / rel
        if chemin.exists():
            blocs.append(f"--- {rel}\n{chemin.read_text(encoding='utf-8')[:limite]}")
    return "\n".join(blocs) or "(socle non disponible)"


def identifiant_ticket(ticket: str) -> str:
    m = re.search(r"^#\s*(NF-\d+)", ticket, re.M)
    return m.group(1) if m else "?"


def construire_message(ticket: str, type_: str, socle: str) -> str:
    return (
        f"Variante : {type_}\n\n<ticket>\n{ticket}\n</ticket>\n\n<socle>\n{socle}\n</socle>\n\n"
        "Liste les questions, hypothèses à valider, contradictions, risques et termes à chiffrer."
    )


def extraire_questions(client: ClientLLM, ticket: str, type_: str, socle: str = "") -> dict[str, Any]:
    """Appelle le modèle (étape « questions »), valide la sortie, renvoie le dossier de questions.

    Contrôles après l'appel (le schéma API seul ne suffit pas) :
    - schéma local strict (identifiants Q-xx / H-xx / R-xx, textes non vides) ;
    - identifiants de questions uniques ;
    - chaque hypothèse porte le numéro de sa question (Q-03 → H-03).
    Lève schemas.SortieInvalide sinon.
    """
    # TODO TP1 : appeler client.json(etape='questions', ...) avec prompt('questions'), construire_message(...) et schemas.QUESTIONS_API, valider avec schemas.QUESTIONS_LOCAL, contrôler doublons et numérotation Q-xx/H-xx.
    raise NotImplementedError("TODO TP1 : extraire_questions")
