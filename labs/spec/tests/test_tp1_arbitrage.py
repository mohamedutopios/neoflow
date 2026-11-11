"""TP 1 — étape 2 : arbitrage humain et porte 1."""
from __future__ import annotations

import pytest

from neospec.arbitrage import PorteNonFranchie, appliquer_reponses, charger_reponses, verifier_porte_1


def _questions(n=3):
    return {"type": "CONGES", "ticket": "NF-401", "contradictions": [], "risques": [], "termes_a_chiffrer": [],
            "questions": [{"id": f"Q-{i:02d}", "question": f"Question {i} ?", "source": "Ticket", "priorite": "Bloquante",
                           "hypothese": {"id": f"H-{i:02d}", "enonce": f"Hypothèse {i}"}} for i in range(1, n + 1)]}


def test_trois_decisions():
    d = appliquer_reponses(_questions(), {"decideur": "Sophie Garnier (DRH)", "date": "2026-11-16", "decisions": {
        "Q-01": "valider",
        "Q-02": {"decision": "remplacer", "hypothese": "Hypothèse réécrite", "decideur": "Bertrand Collin (paie)"},
        "Q-03": {"decision": "rejeter", "motif": "Hors v1"}}})
    h = {x["id"]: x for x in d["hypotheses"]}
    assert h["H-01"]["statut"] == "Validée" and h["H-01"]["enonce"] == "Hypothèse 1"
    assert h["H-02"]["enonce"] == "Hypothèse réécrite" and h["H-02"]["valide_par"] == "Bertrand Collin (paie)"
    assert h["H-03"]["statut"] == "Rejetée" and d["questions"][2]["decision"] == "Hors v1"
    assert all(x["date"] == "2026-11-16" for x in d["hypotheses"])
    verifier_porte_1(d)


def test_ajouts_numerotes():
    d = appliquer_reponses(_questions(2), {"decideur": "DRH", "date": "2026-11-16",
                                           "decisions": {"Q-01": "valider", "Q-02": "valider"},
                                           "ajouts": [{"question": "Durée max ?", "source": "VARIANTES", "decision": "20 jours"},
                                                      {"question": "Motif ?", "source": "VARIANTES", "decision": "Oui",
                                                       "hypothese": "Motif de 20 caractères"}]})
    assert [q["id"] for q in d["questions"]] == ["Q-01", "Q-02", "Q-03", "Q-04"]
    assert d["questions"][2]["hypothese"] is None and d["questions"][3]["hypothese"] == "H-03"
    assert d["hypotheses"][-1] == {"id": "H-03", "enonce": "Motif de 20 caractères", "statut": "Validée",
                                   "valide_par": "DRH", "date": "2026-11-16"}


def test_reponses_invalides():
    with pytest.raises(ValueError):
        appliquer_reponses(_questions(), {"decisions": {"Q-01": "peut-etre"}})
    with pytest.raises(ValueError):
        appliquer_reponses(_questions(), {"decisions": {"Q-01": {"decision": "remplacer"}}})
    with pytest.raises(ValueError):
        appliquer_reponses(_questions(), {"decisions": {"Q-99": "valider"}})


def test_porte_1_question_sans_decision():
    d = appliquer_reponses(_questions(), {"decideur": "DRH", "date": "2026-11-16", "decisions": {"Q-01": "valider"}})
    with pytest.raises(PorteNonFranchie) as e:
        verifier_porte_1(d)
    assert e.value.manquantes == ["Q-02", "Q-03"]


def test_porte_1_decideur_non_humain():
    d = appliquer_reponses(_questions(1), {"decideur": "Claude (agent)", "date": "2026-11-16", "decisions": {"Q-01": "valider"}})
    with pytest.raises(PorteNonFranchie, match="décideur humain"):
        verifier_porte_1(d)


def test_reponses_conges(fixture_questions, reponses_conges):
    d = appliquer_reponses({"type": "CONGES", "ticket": "NF-401", **fixture_questions}, charger_reponses(reponses_conges))
    verifier_porte_1(d)
    assert len(d["questions"]) == 18 and len(d["hypotheses"]) == 15
