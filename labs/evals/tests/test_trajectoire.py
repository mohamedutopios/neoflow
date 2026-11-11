import pytest
import json

from conftest import LAB
from trajectoire import JournalIllisible, classe_commande, lire_journal

EX = LAB / "mesure" / "exemples"
pytestmark = pytest.mark.skipif(not (EX / "j10_structure_stat_types.jsonl").exists(),
                                reason="exemples non installés (profil generique)")


def test_journal_exemple_contrat():
    t = lire_journal(EX / "j10_structure_stat_types.jsonl")
    assert t.statut_fin == "termine"
    assert set(t.usage_par_modele()) == {"claude-sonnet-5-5", "claude-opus-5-5"}
    assert t.usage["input_tokens"] > 0 and t.usage["cache_read_input_tokens"] > 0
    assert len(t.executions_tests()) == 3
    assert len(t.ecritures()) == len(t.approbations) == 6
    assert any("cache_creation_input_tokens absent" in a for a in t.avertissements)


def test_tolerance(tmp_path):
    f = tmp_path / "j.jsonl"
    lignes = [
        "ligne de log parasite",
        json.dumps({"ts": 1793790000, "session": "s", "etape": 1, "type": "llm", "modele": "claude-haiku-5-5",
                    "usage": {"input_tokens": 10, "output_tokens": 2, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 5}}),
        json.dumps({"ts": 1793790001000, "session": "s", "etape": 1, "type": "tool_call", "outil": "lire_fichier", "entree": {"chemin": ".env"}}),
        json.dumps({"ts": "2026-11-04T08:00:02Z", "session": "s", "etape": 1, "type": "tool_result", "outil": "lire_fichier",
                    "sortie_extrait": "REFUS : chemin interdit"}),
        json.dumps({"type": "inconnu_futur"}),
        json.dumps({"ts": "2026-11-04T08:00:03Z", "type": "tool_result", "outil": "lister", "sortie_extrait": "orphelin"}),
    ]
    f.write_text("\n".join(lignes))
    t = lire_journal(f)
    assert t.refus()[0].outil == "lire_fichier"
    assert t.inconnus["ligne_non_json"] == 1 and t.inconnus["type:inconnu_futur"] == 1 and t.inconnus["tool_result_orphelin"] == 1
    assert t.usage["cache_creation_input_tokens"] == 5
    assert any("fin" in a for a in t.avertissements)


def test_dossier_de_workers(tmp_path):
    for i in (1, 2):
        (tmp_path / f"w{i}.jsonl").write_text(json.dumps({"session": f"w{i}", "type": "llm", "modele": "claude-sonnet-5-5",
                                                          "usage": {"input_tokens": 100, "output_tokens": 10}}))
    t = lire_journal(tmp_path)
    assert t.sessions == ["w1", "w2"] and t.usage["input_tokens"] == 200


def test_journal_vide(tmp_path):
    (tmp_path / "v.jsonl").write_text("\n")
    try:
        lire_journal(tmp_path / "v.jsonl")
        assert False
    except JournalIllisible:
        pass


def test_classes_commandes():
    assert classe_commande("cd backend && ./mvnw -q verify") == "tests"
    assert classe_commande("semgrep scan --config p/java") == "scan"
    assert classe_commande("./mvnw -q -DskipTests package") == "build"
