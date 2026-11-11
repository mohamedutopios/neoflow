"""JSON Schemas des sorties structurées.

Deux niveaux :
- le schéma envoyé à l'API (`output_config.format`) n'utilise que le sous-ensemble accepté par
  les sorties structurées : types, enum, required, additionalProperties: false. Pas de pattern,
  ni de minLength, ni de minItems ;
- la validation locale (`valider_json`) ajoute les contraintes strictes : formats d'identifiants,
  listes non vides. C'est elle qui fait foi : une sortie qui ne la passe pas est rejetée.
"""
from __future__ import annotations

import copy
from typing import Any

from jsonschema import Draft202012Validator

from neospec.config import ID_EXIGENCE


class SortieInvalide(ValueError):
    """La sortie du modèle ne respecte pas le schéma local."""

    def __init__(self, erreurs: list[str]):
        super().__init__("Sortie non conforme au schéma : " + " ; ".join(erreurs[:5]))
        self.erreurs = erreurs


def _objet(proprietes: dict[str, Any], requis: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": requis if requis is not None else list(proprietes),
        "properties": proprietes,
    }


TEXTE = {"type": "string"}
LISTE_TEXTES = {"type": "array", "items": TEXTE}

# ------------------------------------------------------------------ étape 1 : questions
QUESTIONS_API: dict[str, Any] = _objet(
    {
        "questions": {
            "type": "array",
            "items": _objet(
                {
                    "id": TEXTE,
                    "question": TEXTE,
                    "source": TEXTE,
                    "priorite": {"type": "string", "enum": ["Bloquante", "Importante", "Confort"]},
                    "hypothese": _objet({"id": TEXTE, "enonce": TEXTE}),
                }
            ),
        },
        "contradictions": {
            "type": "array",
            "items": _objet({"passages": LISTE_TEXTES, "explication": TEXTE}),
        },
        "risques": {"type": "array", "items": _objet({"id": TEXTE, "risque": TEXTE, "mitigation": TEXTE})},
        "termes_a_chiffrer": {"type": "array", "items": _objet({"terme": TEXTE, "question": TEXTE})},
    }
)

# ------------------------------------------------------------------ étape 3 : génération
GENERATION_API: dict[str, Any] = _objet(
    {
        "titre": TEXTE,
        "contexte": TEXTE,
        "user_stories": {"type": "array", "items": _objet({"id": TEXTE, "story": TEXTE, "invest": TEXTE})},
        "non_objectifs": {"type": "array", "items": _objet({"id": TEXTE, "objectif": TEXTE, "raison": TEXTE})},
        "regles": {
            "type": "array",
            "items": _objet({"id": TEXTE, "regle": TEXTE, "code": TEXTE, "exemple": TEXTE}),
        },
        "exigences": {
            "type": "array",
            "items": _objet(
                {
                    "id": TEXTE,
                    "titre": TEXTE,
                    "enonce": TEXTE,
                    "priorite": {"type": "string", "enum": ["Must", "Should", "Could"]},
                    "regles": LISTE_TEXTES,
                    "verification": TEXTE,
                }
            ),
        },
        "exigences_non_fonctionnelles": {
            "type": "array",
            "items": _objet({"id": TEXTE, "titre": TEXTE, "enonce": TEXTE, "preuve": TEXTE}),
        },
        "contraintes": {"type": "array", "items": _objet({"id": TEXTE, "contrainte": TEXTE})},
        "risques": {"type": "array", "items": _objet({"id": TEXTE, "risque": TEXTE, "mitigation": TEXTE})},
        "features": {"type": "array", "items": _objet({"fichier": TEXTE, "contenu": TEXTE})},
        "openapi_delta": TEXTE,
        "matrice": {
            "type": "array",
            "items": _objet(
                {
                    "exigence": TEXTE,
                    "regles": TEXTE,
                    "scenarios": TEXTE,
                    "contrat": TEXTE,
                    "taches": TEXTE,
                    "tests_prevus": TEXTE,
                }
            ),
        },
        "plan": {
            "type": "array",
            "items": _objet(
                {
                    "id": TEXTE,
                    "nature": {"type": "string", "enum": ["D", "A", "H"]},
                    "tache": TEXTE,
                    "depend_de": LISTE_TEXTES,
                    "exigences": LISTE_TEXTES,
                    "fichiers": TEXTE,
                    "verification": TEXTE,
                }
            ),
        },
        "adr": _objet(
            {
                "titre": TEXTE,
                "slug": TEXTE,
                "contexte": TEXTE,
                "options": {
                    "type": "array",
                    "items": _objet({"nom": TEXTE, "description": TEXTE, "avantages": TEXTE, "inconvenients": TEXTE}),
                },
                "recommandation": TEXTE,
                "consequences_negatives": TEXTE,
                "indicateur_remise_en_cause": TEXTE,
                "exigences": LISTE_TEXTES,
            }
        ),
    }
)


# ------------------------------------------------------------------ contraintes locales
def _strict_questions() -> dict[str, Any]:
    s = copy.deepcopy(QUESTIONS_API)
    q = s["properties"]["questions"]
    q["minItems"] = 1
    q["items"]["properties"]["id"] = {"type": "string", "pattern": r"^Q-\d{2,3}$"}
    q["items"]["properties"]["question"] = {"type": "string", "minLength": 10}
    q["items"]["properties"]["source"] = {"type": "string", "minLength": 3}
    q["items"]["properties"]["hypothese"]["properties"]["id"] = {"type": "string", "pattern": r"^H-\d{2,3}$"}
    s["properties"]["risques"]["items"]["properties"]["id"] = {"type": "string", "pattern": r"^R-\d{2,3}$"}
    return s


def _strict_generation() -> dict[str, Any]:
    s = copy.deepcopy(GENERATION_API)
    p = s["properties"]
    p["exigences"]["minItems"] = 1
    p["exigences"]["items"]["properties"]["id"] = {"type": "string", "pattern": rf"^{ID_EXIGENCE}$"}
    p["exigences_non_fonctionnelles"]["items"]["properties"]["id"] = {"type": "string", "pattern": rf"^{ID_EXIGENCE}$"}
    p["regles"]["items"]["properties"]["id"] = {"type": "string", "pattern": r"^RM-\d{2,3}$"}
    p["regles"]["items"]["properties"]["code"] = {"type": "string", "pattern": r"^(|[A-Z][A-Z0-9_]+)$"}
    p["features"]["minItems"] = 1
    p["features"]["items"]["properties"]["fichier"] = {"type": "string", "pattern": r"^[a-z0-9_-]+\.feature$"}
    p["openapi_delta"] = {"type": "string", "minLength": 50}
    p["plan"]["items"]["properties"]["id"] = {"type": "string", "pattern": r"^T\d{2}$"}
    p["adr"]["properties"]["slug"] = {"type": "string", "pattern": r"^[a-z0-9-]+$"}
    p["adr"]["properties"]["options"]["minItems"] = 3
    return s


QUESTIONS_LOCAL = _strict_questions()
GENERATION_LOCAL = _strict_generation()


def valider_json(donnees: Any, schema: dict[str, Any]) -> None:
    """Lève SortieInvalide avec la liste des écarts (chemin JSON et message)."""
    erreurs = [
        f"{'/'.join(str(x) for x in e.absolute_path) or '(racine)'} : {e.message}"
        for e in sorted(Draft202012Validator(schema).iter_errors(donnees), key=lambda e: list(e.absolute_path))
    ]
    if erreurs:
        raise SortieInvalide(erreurs)
