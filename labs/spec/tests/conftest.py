"""Fixtures communes. Aucun test n'appelle l'API : le modèle est simulé ou doublé."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[1]
DONNEES = Path(__file__).resolve().parent / "donnees"


@pytest.fixture(autouse=True)
def sans_cle(monkeypatch):
    """Garantit qu'aucun test ne peut consommer une clé présente dans l'environnement."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


@pytest.fixture
def racine(tmp_path: Path) -> Path:
    """Dépôt NeoFlow minimal : tickets et dossier d'ADR."""
    (tmp_path / "docs" / "tickets").mkdir(parents=True)
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    for f in DONNEES.glob("ticket_*.md"):
        shutil.copy(f, tmp_path / "docs" / "tickets" / f.name.removeprefix("ticket_"))
    return tmp_path


@pytest.fixture
def fixture_generation() -> dict:
    return json.loads((LAB / "fixtures" / "offline" / "CONGES" / "generation.json").read_text(encoding="utf-8"))


@pytest.fixture
def fixture_questions() -> dict:
    return json.loads((LAB / "fixtures" / "offline" / "CONGES" / "questions.json").read_text(encoding="utf-8"))


@pytest.fixture
def reponses_conges() -> Path:
    return LAB / "exemples" / "reponses_CONGES.yaml"
