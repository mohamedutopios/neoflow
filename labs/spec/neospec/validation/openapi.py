"""Contrôle du contrat delta : validité OpenAPI (openapi-spec-validator) puis conventions NeoFlow."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from neospec.config import RE_ID_EXIGENCE
from neospec.validation.rapport import Rapport

METHODES = ("get", "put", "post", "delete", "patch")


def _resoudre(spec: dict[str, Any], objet: dict[str, Any]) -> dict[str, Any]:
    ref = objet.get("$ref") if isinstance(objet, dict) else None
    if not ref or not ref.startswith("#/"):
        return objet
    cible: Any = spec
    for morceau in ref[2:].split("/"):
        cible = cible.get(morceau, {}) if isinstance(cible, dict) else {}
    return cible


BASE = "urn:neoflow:contrat"


def _pointeur(*morceaux: str) -> str:
    return "#/" + "/".join(str(m).replace("~", "~0").replace("/", "~1") for m in morceaux)


def exemples_invalides(spec: dict[str, Any]) -> list[str]:
    """Exemples de corps (requêtes et réponses) non conformes à leur schéma (JSON Schema 2020-12)."""
    registre = Registry().with_resource(BASE, Resource(contents=spec, specification=DRAFT202012))
    ecarts: list[str] = []

    def controler(contenu: dict[str, Any], *chemin: str) -> None:
        for media, corps in (contenu or {}).items():
            if not isinstance(corps, dict) or "schema" not in corps:
                continue
            valeurs = []
            if "example" in corps:
                valeurs.append(("example", corps["example"]))
            for nom, ex in (corps.get("examples") or {}).items():
                if isinstance(ex, dict) and "value" in ex:
                    valeurs.append((f"examples/{nom}", ex["value"]))
            validateur = Draft202012Validator({"$ref": BASE + _pointeur(*chemin, "content", media, "schema")}, registry=registre)
            for nom, valeur in valeurs:
                for e in list(validateur.iter_errors(valeur))[:3]:
                    lieu = "/".join(str(x) for x in e.absolute_path) or "(racine)"
                    ecarts.append(f"{' '.join(chemin[:3])} {media} {nom} : {lieu} : {e.message}")

    for chemin_api, item in (spec.get("paths") or {}).items():
        for methode in METHODES:
            op = (item or {}).get(methode)
            if not isinstance(op, dict):
                continue
            corps = op.get("requestBody")
            if isinstance(corps, dict) and "content" in corps:
                controler(corps["content"], "paths", chemin_api, methode, "requestBody")
            for code, rep in (op.get("responses") or {}).items():
                if isinstance(rep, dict) and "content" in rep:
                    controler(rep["content"], "paths", chemin_api, methode, "responses", str(code))
    for nom, rep in ((spec.get("components") or {}).get("responses") or {}).items():
        if isinstance(rep, dict) and "content" in rep:
            controler(rep["content"], "components", "responses", nom)
    return ecarts


def valider_contrat(chemin: Path, exigences: dict[str, str], rapport: Rapport, nom: str | None = None) -> list[str]:
    """Valide un contrat delta et renvoie les exigences citées dans `x-exigences`.

    Erreurs :
    - YAML illisible, ou document non conforme à OpenAPI 3.x (openapi-spec-validator) ;
    - opération sans `operationId`, `operationId` dupliqué, opération sans `summary` ;
    - opération sans étiquette, ou étiquette non déclarée (avec description) dans `tags` ;
    - opération sans aucune réponse 4xx ;
    - `x-exigences` citant une exigence inconnue de la spécification ;
    - exemple (requête ou réponse) non conforme à son schéma (`exemples_invalides`).
    Avertissements :
    - opération sans `x-exigences`, ou `x-neoflow-delta` absent ou hors de {nouveau, modifie} ;
    - réponse 4xx avec un corps autre que `application/problem+json` ;
    - composant (schéma, réponse, paramètre) jamais référencé.
    """
    # TODO TP3 : yaml.safe_load, validate(spec), puis pour chaque opération : operationId, summary, tags déclarés, réponse 4xx, x-neoflow-delta, x-exigences connues ; composants non référencés.
    raise NotImplementedError("TODO TP3 : valider_contrat")
