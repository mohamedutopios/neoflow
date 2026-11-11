"""Fixtures : un petit dépôt Git à la forme de NeoFlow, sans réseau ni clé."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

FICHIERS = {
    "backend/src/main/java/com/neosoft/neoflow/conges/RegleConges.java":
        "package com.neosoft.neoflow.conges;\n\npublic class RegleConges {\n    int dureeMax() { return 20; }\n}\n",
    "backend/src/test/java/com/neosoft/neoflow/conges/RegleCongesTest.java":
        "class RegleCongesTest {\n    @Tag(\"EF-06\") void dureeMax() { assertEquals(20, regle.dureeMax()); }\n}\n",
    "backend/src/main/java/com/neosoft/neoflow/legacy/RegleValidationLegacy.java": "class RegleValidationLegacy {}\n",
    "backend/pom.xml": "<project/>\n",
    "frontend/src/pages/DemandeFormulaire.tsx": "export function DemandeFormulaire() { return null; }\n",
    "docs/specs/CONGES.md": "# Spécification CONGES\nEF-06 : 20 jours ouvrés au plus.\n",
    ".env": "ANTHROPIC_API_KEY=sk-ant-faux\n",
    ".gitignore": ".env\n",
}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def depot(tmp_path: Path) -> Path:
    repo = tmp_path / "neoflow"
    for chemin, contenu in FICHIERS.items():
        f = repo / chemin
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(contenu, encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@neoflow.example")
    git(repo, "config", "user.name", "Test")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "socle")
    return repo


def outil(nom: str, entree: dict) -> dict:
    """Bloc tool_use en forme courte pour les scénarios simulés."""
    return {"outil": nom, "entree": entree}


def texte(t: str) -> dict:
    return {"texte": t}
