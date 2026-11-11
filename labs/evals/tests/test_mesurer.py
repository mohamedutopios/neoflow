import pytest
import json

import mesurer
from conftest import LAB

EX = LAB / "mesure" / "exemples"
pytestmark = pytest.mark.skipif(not (EX / "j10_structure_stat_types.jsonl").exists(),
                                reason="exemples non installés (profil generique)")
TARIFS = str(EX / "tarifs_fictifs.yaml")


def test_avant_apres(tmp_path, capsys):
    assert mesurer.main([str(EX / "j01_baseline_opencode.fiche.json"), str(EX / "j10_structure_stat_types.jsonl"),
                         "--label", "J1", "--label", "J10", "--tarifs", TARIFS, "--format", "json"]) == 0
    j1, j10 = json.loads(capsys.readouterr().out)
    assert j1["source"] == "opencode" and j10["source"] == "neoagent"
    assert (j1["delai_bout_en_bout_min"], j10["delai_bout_en_bout_min"]) == (46.0, 27.0)
    assert j10["cout_formule"] == round(sum(j10["cout_par_modele"].values()), 6)
    assert j10["approbations"]["total"] == 6 and j10["defauts"]["avant_pr"] == 1


def test_vibe_structure_avec_controles(capsys):
    mesurer.main([str(EX / "extension_vibe.jsonl"), str(EX / "extension_structure.jsonl"), "--label", "vibe",
                  "--label", "structure", "--format", "json"])
    vibe, structure = json.loads(capsys.readouterr().out)
    assert vibe["controles"]["semgrep"] == "KO" and vibe["controles"]["tests ajoutés"] == 0
    assert structure["controles"]["e2e"] == "OK" and structure["defauts"]["total"] == 1


def test_tarifs_incomplets(capsys):
    mesurer.main([str(EX / "j10_structure_stat_types.jsonl"), "--tarifs", str(LAB / "mesure" / "tarifs.example.yaml"),
                  "--format", "json"])
    m = json.loads(capsys.readouterr().out)
    assert m["cout_formule"] is None and any("prix manquants" in a for a in m["avertissements"])
