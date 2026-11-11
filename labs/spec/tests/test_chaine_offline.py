"""Chaîne complète hors ligne, par la ligne de commande (aucun appel à l'API)."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from neospec.cli import main

LAB = Path(__file__).resolve().parents[1]


def test_chaine_conges(racine, reponses_conges, tmp_path):
    code = main(["chaine", "--type", "CONGES", "--racine", str(racine), "--reponses", str(reponses_conges), "--offline",
                 "--journal", str(tmp_path / "j.jsonl"), "--types-parametres", str(LAB / "exemples" / "parametres_CONGES.yaml"),
                 "--runner"])
    assert code == 0
    s = racine / "docs" / "specs"
    assert "| Statut | EN REVUE |" in (s / "CONGES.md").read_text(encoding="utf-8")
    assert len(list((s / "conges" / "features").glob("*.feature"))) == 6
    assert (racine / "docs" / "adr" / "ADR-001-debit-solde-conges.md").exists()
    steps = racine / "backend" / "src" / "test" / "java" / "com" / "neosoft" / "neoflow" / "acceptance" / "conges"
    assert (steps / "CongesSteps.java").exists() and (steps / "AcceptanceCongesTest.java").exists()
    etapes = [json.loads(l)["etape"] for l in (tmp_path / "j.jsonl").read_text().splitlines()]
    assert etapes == ["questions", "generation"]
    assert main(["valider", "--type", "CONGES", "--racine", str(racine)]) == 0


def test_chaine_avec_correction(racine, reponses_conges, tmp_path):
    code = main(["chaine", "--type", "CONGES", "--racine", str(racine), "--reponses", str(reponses_conges), "--offline",
                 "--offline-defaut", "gherkin", "--journal", str(tmp_path / "j.jsonl")])
    assert code == 0
    etapes = [json.loads(l)["etape"] for l in (tmp_path / "j.jsonl").read_text().splitlines()]
    assert etapes == ["questions", "generation", "correction"]


def test_correction_epuisee(racine, reponses_conges, tmp_path):
    code = main(["chaine", "--type", "CONGES", "--racine", str(racine), "--reponses", str(reponses_conges), "--offline",
                 "--offline-defaut", "gherkin-persistant", "--max-corrections", "1", "--journal", str(tmp_path / "j.jsonl")])
    assert code == 2
    assert "| Statut | BROUILLON |" in (racine / "docs" / "specs" / "CONGES.md").read_text(encoding="utf-8")
    assert main(["valider", "--type", "CONGES", "--racine", str(racine)]) == 1


def test_variante_sans_fixture_pas_a_pas(racine, tmp_path):
    """Plan B pour n'importe quelle variante : questions génériques, arbitrage, génération minimale valide."""
    journal = ["--journal", str(tmp_path / "j.jsonl")]
    assert main(["questions", "--type", "MATERIEL_IT", "--racine", str(racine), "--offline", *journal]) == 0
    questions = json.loads((racine / "docs" / "specs" / "materiel-it" / "neospec" / "questions.json").read_text(encoding="utf-8"))
    reponses = tmp_path / "rep.yaml"
    reponses.write_text(yaml.safe_dump({"decideur": "Karim Haddad (DSI)", "date": "2026-11-16",
                                        "decisions": {q["id"]: "valider" for q in questions["questions"]}}), encoding="utf-8")
    assert main(["arbitrer", "--type", "MATERIEL_IT", "--racine", str(racine), "--reponses", str(reponses)]) == 0
    assert main(["generer", "--type", "MATERIEL_IT", "--racine", str(racine), "--offline", *journal]) == 0
    assert main(["valider", "--type", "MATERIEL_IT", "--racine", str(racine)]) == 0


def test_porte_1_refusee_par_la_cli(racine, tmp_path):
    reponses = tmp_path / "rep.yaml"
    reponses.write_text("decideur: DRH\ndate: 2026-11-16\ndecisions:\n  Q-01: valider\n", encoding="utf-8")
    code = main(["chaine", "--type", "CONGES", "--racine", str(racine), "--reponses", str(reponses), "--offline",
                 "--journal", str(tmp_path / "j.jsonl")])
    assert code == 2
    assert not (racine / "docs" / "specs" / "CONGES.md").exists()


def test_controles_autonomes(tmp_path, fixture_generation):
    contrat = tmp_path / "delta.yaml"
    contrat.write_text(fixture_generation["openapi_delta"], encoding="utf-8")
    assert main(["contrat", str(contrat)]) == 0
    mauvais = tmp_path / "mauvais.feature"
    mauvais.write_text("# language: fr\nFonctionnalité: X\n  Scénario: Test 1\n    Quand alice soumet\n    Alors ok\n", encoding="utf-8")
    assert main(["gherkin", str(mauvais)]) == 1
