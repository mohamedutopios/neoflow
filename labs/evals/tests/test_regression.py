import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import run_regression as rr
from conftest import LAB

STUBS = Path(__file__).parent / "stubs"
EX = LAB / "regression_prompts" / "exemples_runs"


@pytest.mark.skipif(not EX.exists(), reason="enregistrements d'exemple non installés (profil generique)")
def test_rejeu_et_comparaison(tmp_path):
    assert rr.main(["--rejouer", str(EX / "config-A"), "--label", "A", "--sortie", str(tmp_path)]) == 0
    code = rr.main(["--rejouer", str(EX / "config-B"), "--label", "B", "--sortie", str(tmp_path),
                    "--reference", str(tmp_path / "A.json")])
    assert code == 1
    ecarts = {e["id"]: e["ecart"] for e in json.loads((tmp_path / "B.json").read_text())["comparaison"]}
    assert ecarts["NA05"] == "REGRESSION" and ecarts["NA06"] == "BAISSE" and ecarts["NA03"] == "STABLE_OK"


def test_wilson_et_seuil():
    assert rr.wilson_bas(3, 3) == 0.438 and rr.lire_seuil("2/3") < 0.67


@pytest.mark.skipif(not (LAB / "rag_questions.yaml").exists(), reason="jeu du J05 absent")
def test_jeu_j05_en_cas_neoagent():
    cas = rr.cas_depuis_rag(rr.charger_questions_rag(LAB / "rag_questions.yaml"), "rag\\w*", ["rag.agent_tool:rag_tool"])
    assert len(cas) >= 15 and cas[0]["outils_externes"] == ["rag.agent_tool:rag_tool"]


def depot(tmp_path):
    d = tmp_path / "depot"
    d.mkdir()
    for c in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"], ["git", "config", "user.name", "t"]):
        subprocess.run(c, cwd=d, check=True)
    (d / "README.md").write_text("x\n")
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=d, check=True)
    return d


def test_execution_offline_worktree_avec_faux_neoagent(tmp_path, monkeypatch):
    d = depot(tmp_path)
    cas = tmp_path / "cas"
    cas.mkdir()
    (cas / "X01.yaml").write_text(
        "id: X01\noutil: neoagent\nworktree: true\npattern: generator_verifier\nmode: structure\n"
        "outils_externes: ['rag.agent_tool:rag_tool']\ntache: |\n  Tâche avec espaces\n  et deux lignes\n"
        "criteres:\n  - {id: C1, type: approbation_avant_ecriture}\n  - {id: C2, type: tests_apres_ecriture}\n"
        "  - {id: C3, type: sortie_contient, motifs: ['offline=True', 'externes=rag.agent_tool:rag_tool', 'tache=Tâche avec espaces']}\n"
        "  - {id: C4, type: fichiers_modifies, inclus: ['backend/src/main/java/**']}\n"
        "  - {id: C5, type: commande, cmd: 'test -f backend/src/main/java/Exemple.java', code_attendu: 0}\n"
        "  - {id: C6, type: pas_de_boucle}\n  - {id: C7, type: boucle_verification, min: 1}\n")
    monkeypatch.chdir(d)
    monkeypatch.syspath_prepend(str(STUBS))
    cmd = (f"{sys.executable} {STUBS / 'faux_neoagent.py'} --repo {{repo}} --tache {{tache}} --pattern {{pattern}} "
           "--mode {mode} --journal {journal} {offline} {ecriture} {approbation} {outils_externes}")
    code = rr.main(["--cas", str(cas), "--worktree", "--label", "t", "--sortie", str(tmp_path / "res"),
                    "--neoagent-cmd", cmd, "--criteres-externes", "criteres_perso"])
    res = json.loads((tmp_path / "res" / "t.json").read_text())
    criteres = {c["id"]: c["ok"] for c in res["cas"][0]["runs"][0]["criteres"]}
    assert code == 0, criteres
    assert all(criteres.values())
    assert subprocess.run(["git", "status", "--porcelain"], cwd=d, capture_output=True, text=True).stdout == ""
    worktrees = subprocess.run(["git", "worktree", "list"], cwd=d, capture_output=True, text=True).stdout.strip().splitlines()
    assert len(worktrees) == 1          # le worktree jetable a été supprimé


def test_outil_commande_neospec_offline(tmp_path, monkeypatch):
    """Forme réelle de PS01 : `neospec chaine … --racine {repo} --journal {journal} {offline}`, écrit dans le worktree."""
    d = depot(tmp_path)
    cas = tmp_path / "cas"
    cas.mkdir()
    (cas / "S01.yaml").write_text(
        "id: S01\noutil: commande\nworktree: true\n"
        "commande: \"${SPEC_CMD:-introuvable} chaine --type CONGES --reponses r.yaml --racine {repo} --journal {journal} {offline}\"\n"
        "criteres:\n  - {id: C1, type: code_retour, attendu: 0}\n"
        "  - {id: C2, type: sortie_contient, motifs: ['\\[5/5\\]', 'EN REVUE']}\n"
        "  - {id: C3, type: fichiers_modifies, inclus: ['docs/specs/CONGES.md', 'docs/specs/conges/features/*.feature'], exclus: ['backend/**']}\n"
        "  - {id: C4, type: commande, cmd: \"grep -q 'EF-01' docs/specs/CONGES.md\", code_attendu: 0}\n")
    monkeypatch.chdir(d)
    monkeypatch.setenv("SPEC_CMD", f"{sys.executable} {STUBS / 'faux_spec.py'}")
    assert rr.main(["--cas", str(cas), "--worktree", "--label", "s", "--sortie", str(tmp_path / "res")]) == 0
    run = json.loads((tmp_path / "res" / "s.json").read_text())["cas"][0]["runs"][0]
    assert all(c["ok"] for c in run["criteres"]), run["criteres"]
    assert run["tokens_total"] == 3400            # journal d'usage sans « type », lu comme appels llm


def test_outil_commande_tests_ia_dossier_et_fichier_sortie(tmp_path, monkeypatch):
    """Forme réelle de PT01 : --sortie {dossier}, rapport lu par fichier_sortie, contrôle sur {dossier}."""
    d = depot(tmp_path)
    cas = tmp_path / "cas"
    cas.mkdir()
    (cas / "T01.yaml").write_text(
        "id: T01\noutil: commande\nfichier_sortie: rapport-generation.md\n"
        f"commande: \"{sys.executable} {STUBS / 'faux_tests_ia.py'} generer --projet backend --classe a.B --spec s.md "
        "--sortie {dossier} --journal {journal} --sans-mutation {offline}\"\n"
        "criteres:\n  - {id: C1, type: sortie_contient, motifs: ['\\| ACCEPTE \\|']}\n"
        "  - {id: C2, type: commande, cmd: \"find {dossier}/acceptes -name '*.java' | grep -q .\", code_attendu: 0}\n"
        "  - {id: C3, type: sans_erreur}\n")
    monkeypatch.chdir(d)
    assert rr.main(["--cas", str(cas), "--label", "t", "--sortie", str(tmp_path / "res")]) == 0
    run = json.loads((tmp_path / "res" / "t.json").read_text())["cas"][0]["runs"][0]
    assert all(c["ok"] for c in run["criteres"]), run["criteres"]
    assert run["appels_outils"] == 1


def test_reel_exige_une_cle(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert rr.main(["--reel", "--sortie", str(tmp_path)]) == 2
