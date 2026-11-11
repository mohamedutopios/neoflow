"""TP fil rouge — génération (porte 1 avant tout appel) et boucle de correction bornée."""
from __future__ import annotations

import pytest

from neospec.arbitrage import PorteNonFranchie, appliquer_reponses, charger_reponses
from neospec.correction import boucle_correction
from neospec.generation import ecrire_artefacts, generer
from neospec.llm import ClientSimule
from neospec.rendu import EcritureInterdite, chemin_autorise


@pytest.fixture
def decisions(fixture_questions, reponses_conges):
    return appliquer_reponses({"type": "CONGES", "ticket": "NF-401", **fixture_questions}, charger_reponses(reponses_conges))


def test_pas_de_generation_sans_porte_1(fixture_questions):
    d = appliquer_reponses({"type": "CONGES", **fixture_questions}, {"decideur": "DRH", "date": "2026-11-16",
                                                                      "decisions": {"Q-01": "valider"}})
    client = ClientSimule("CONGES")
    with pytest.raises(PorteNonFranchie):
        generer(client, "# NF-401", "CONGES", d)
    assert client.appels == []


def test_generation_transmet_les_decisions(decisions):
    client = ClientSimule("CONGES")
    g = generer(client, "# NF-401", "CONGES", decisions)
    assert len(g["exigences"]) == 16
    message = client.appels[0]["message"]
    assert "<decisions>" in message and "Bertrand Collin (paie)" in message


def test_correction_d_un_gherkin_invalide(racine, decisions):
    client = ClientSimule("CONGES", defaut="gherkin")
    g = generer(client, "# NF-401", "CONGES", decisions)
    r = boucle_correction(client, racine, "CONGES", decisions, g, max_corrections=2)
    assert r.ok and r.corrections == 1
    assert r.historique[0]["erreurs"] > 0 and r.historique[-1]["erreurs"] == 0
    correction = client.appels[-1]
    assert correction["etape"] == "correction" and "language" in correction["message"]


def test_boucle_bornee(racine, decisions):
    client = ClientSimule("CONGES", defaut="gherkin-persistant")
    g = generer(client, "# NF-401", "CONGES", decisions)
    r = boucle_correction(client, racine, "CONGES", decisions, g, max_corrections=2)
    assert not r.ok and r.corrections == 2 and len(r.historique) == 3
    assert sum(1 for a in client.appels if a["etape"] == "correction") == 2


def test_sans_defaut_aucune_correction(racine, decisions):
    client = ClientSimule("CONGES")
    r = boucle_correction(client, racine, "CONGES", decisions, generer(client, "# NF-401", "CONGES", decisions))
    assert r.ok and r.corrections == 0


def test_garde_fous_ecriture(racine, decisions, fixture_generation):
    with pytest.raises(EcritureInterdite):
        chemin_autorise(racine, racine / "backend" / "src" / "main" / "java" / "X.java")
    ecrire_artefacts(racine, "CONGES", decisions, fixture_generation)
    spec = racine / "docs" / "specs" / "CONGES.md"
    spec.write_text(spec.read_text(encoding="utf-8").replace("| Statut | EN REVUE |", "| Statut | PRÊTE |"), encoding="utf-8")
    with pytest.raises(EcritureInterdite, match="PRÊTE"):
        ecrire_artefacts(racine, "CONGES", decisions, fixture_generation)


def test_brouillons_transmis(decisions):
    client = ClientSimule("CONGES")
    generer(client, "# NF-401", "CONGES", decisions, brouillons="--- conges_brouillon.feature\n# language: fr")
    assert "<brouillons>" in client.appels[0]["message"] and "conges_brouillon.feature" in client.appels[0]["message"]
