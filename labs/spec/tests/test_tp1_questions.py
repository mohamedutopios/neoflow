"""TP 1 — étape 1 : extraction et contrôle des questions."""
from __future__ import annotations

import copy

import pytest

from neospec.llm import ClientSimule
from neospec.questions import extraire_questions
from neospec.schemas import SortieInvalide


class ClientFige:
    def __init__(self, sortie):
        self.sortie = sortie
        self.appels = []

    def json(self, **kw):
        self.appels.append(kw)
        return copy.deepcopy(self.sortie)


def test_questions_conges(racine):
    ticket = (racine / "docs" / "tickets" / "CONGES.md").read_text(encoding="utf-8")
    client = ClientSimule("CONGES")
    q = extraire_questions(client, ticket, "CONGES")
    assert q["type"] == "CONGES" and q["ticket"] == "NF-401"
    assert [x["id"] for x in q["questions"]][:3] == ["Q-01", "Q-02", "Q-03"]
    assert client.appels[0]["etape"] == "questions"
    assert "NF-401" in client.appels[0]["message"]


def test_identifiants_dupliques(fixture_questions):
    sortie = copy.deepcopy(fixture_questions)
    sortie["questions"][1]["id"] = "Q-01"
    sortie["questions"][1]["hypothese"]["id"] = "H-01"
    with pytest.raises(SortieInvalide, match="dupliqués"):
        extraire_questions(ClientFige(sortie), "# NF-401", "CONGES")


def test_hypothese_mal_numerotee(fixture_questions):
    sortie = copy.deepcopy(fixture_questions)
    sortie["questions"][2]["hypothese"]["id"] = "H-09"
    with pytest.raises(SortieInvalide, match="Q-03"):
        extraire_questions(ClientFige(sortie), "# NF-401", "CONGES")


def test_schema_local_strict(fixture_questions):
    sortie = copy.deepcopy(fixture_questions)
    sortie["questions"][0]["id"] = "Q1"
    with pytest.raises(SortieInvalide):
        extraire_questions(ClientFige(sortie), "# NF-401", "CONGES")
