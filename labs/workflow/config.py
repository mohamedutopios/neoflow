"""Configuration du lab : valeurs par défaut + surcharge par config.yaml (ou --config)."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

ICI = Path(__file__).resolve().parent

DEFAUTS: dict[str, Any] = {
    "modeles": {"routage": "claude-haiku-5-5", "redaction": "claude-sonnet-5-5"},
    "budget": {"appels_llm": 6, "tokens": 40_000},
    "limites": {
        "recursion_limit": 25,
        "max_relances": 2,
        "timeout_source_s": 20.0,
        "timeout_llm_s": 60.0,
    },
    "retries": {"max_tentatives": 3, "intervalle_initial_s": 0.2, "facteur": 2.0, "jitter": True},
    "preuves": {"min_resultats": 2, "min_resultats_git": 1, "couverture_min": 0.5, "k": 5},
    "actions_sensibles": ["commenter_ticket", "deleguer_neoagent"],
    "portee_defaut": "projet:neoflow",
    "routage": {"glossaire": {}},
    "extensions": {"politique_memoire": None, "verdict_souvenir": None, "routeur": None, "source_suivante": None,
                   "noeuds": None, "classer_changements": None},
    "neoagent": {"chemin_lab": "../agent", "modele": "claude-sonnet-5-5", "max_etapes": 15,
                 "budget_tokens": 60_000},
    "rag": {"activer": "auto", "chemin_lab": "../rag"},
    "memoire": {"ttl_jours": {"episodique": 30, "semantique": 90, "procedurale": None}},
    "reindex": {
        "inclure": ["**/*.java", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.md", "**/*.yml", "**/*.yaml", "**/*.sql"],
        "exclure": ["**/node_modules/**", "**/target/**", "**/dist/**", "**/.etat/**", "**/*.min.js"],
        "taille_max_ko": 200,
        "lignes_par_chunk_simule": 40,
    },
}


def _fusion(base: dict, surcharge: dict) -> dict:
    out = copy.deepcopy(base)
    for cle, val in (surcharge or {}).items():
        if isinstance(val, dict) and isinstance(out.get(cle), dict):
            out[cle] = _fusion(out[cle], val)
        else:
            out[cle] = val
    return out


def charger(chemin: str | Path | None = None) -> dict[str, Any]:
    """Ordre : DEFAUTS < config.yaml du lab < fichier passé en argument < variables d'environnement."""
    cfg = copy.deepcopy(DEFAUTS)
    cfg["_base"] = str(ICI)            # base de résolution des chemins d'extensions
    candidats = [ICI / "config.yaml"] + ([Path(chemin)] if chemin else [])
    for c in candidats:
        if c and Path(c).is_file():
            cfg = _fusion(cfg, yaml.safe_load(Path(c).read_text(encoding="utf-8")) or {})
            cfg["_base"] = str(Path(c).resolve().parent)
    if os.environ.get("NEOFLOW_RAG", "").lower() in {"off", "non", "0"}:
        cfg["rag"]["activer"] = "non"
    return cfg


def dossier_etat(valeur: str | Path | None = None) -> Path:
    """Dossier des fichiers d'exécution (checkpoints, effets, mémoire, journal). Jamais versionné."""
    d = Path(valeur or os.environ.get("NEOFLOW_ETAT") or ICI / ".etat")
    d.mkdir(parents=True, exist_ok=True)
    return d
