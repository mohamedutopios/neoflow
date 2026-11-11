from __future__ import annotations

import json
from pathlib import Path

from conftest import git

from neoagent.cli import charger_outils_externes, main
from neoagent.journal import lire_journal
from neoagent.tools import Tool


def test_cli_offline_react_avec_journal(depot: Path, tmp_path: Path, capsys):
    code = main(["--repo", str(depot), "--tache", "Où est la méthode dureeMax de RegleConges ?", "--offline",
                 "--journal", str(tmp_path / "traj.jsonl")])
    rapport = json.loads(capsys.readouterr().out)
    assert code == 0 and rapport["resultat"]["statut"] == "termine" and rapport["offline"]
    assert lire_journal(tmp_path / "traj.jsonl")[-1]["type"] == "fin"


def test_cli_script_generator_verifier_offline(depot: Path, tmp_path: Path, capsys):
    script = tmp_path / "scenario.json"
    script.write_text(json.dumps({"tours": [
        [{"outil": "editer_fichier", "entree": {"chemin": "backend/src/main/java/com/neosoft/neoflow/conges/RegleConges.java",
                                                "ancien": "return 20;", "nouveau": "return 20; // EF-06"}}],
        [{"texte": "Fait."}]]}))
    code = main(["--repo", str(depot), "--tache", "T07", "--offline", "--script", str(script), "--pattern",
                 "generator_verifier", "--ecriture", "--approbation", "accord", "--verificateur", "git status",
                 "--verificateur-repertoire", "."])
    rapport = json.loads(capsys.readouterr().out)
    assert code == 0 and rapport["statut"] == "verifie" and rapport["tours"] == 1


def test_cli_ecriture_refusee_par_defaut_hors_terminal(depot: Path, tmp_path: Path, capsys):
    script = tmp_path / "s.json"
    script.write_text(json.dumps({"tours": [
        [{"outil": "editer_fichier", "entree": {"chemin": "frontend/src/x.ts", "nouveau": "x"}}], [{"texte": "refusé"}]]}))
    main(["--repo", str(depot), "--tache", "x", "--offline", "--script", str(script), "--ecriture"])
    assert not (depot / "frontend/src/x.ts").exists()  # stdin non interactif → approbation « refus »


def test_cli_mode_vibe_change_le_prompt_pas_les_garde_fous(depot: Path, tmp_path: Path, capsys):
    script = tmp_path / "s.json"
    script.write_text(json.dumps({"tours": [
        [{"outil": "executer_commande", "entree": {"commande": "rm -rf backend"}}], [{"texte": "ok"}]]}))
    main(["--repo", str(depot), "--tache", "x", "--offline", "--script", str(script), "--mode", "vibe",
          "--ecriture", "--approbation", "accord"])
    assert (depot / "backend").exists()


def test_cli_commit_apres_approbation(depot: Path, tmp_path: Path, capsys):
    script = tmp_path / "s.json"
    script.write_text(json.dumps({"tours": [
        [{"outil": "editer_fichier", "entree": {"chemin": "frontend/src/api/conges.ts", "nouveau": "export {}\n"}}],
        [{"texte": "fait"}]]}))
    main(["--repo", str(depot), "--tache", "x", "--offline", "--script", str(script), "--ecriture",
          "--approbation", "accord", "--commit", "feat(conges): api [EF-13]"])
    assert "feat(conges): api [EF-13]" in git(depot, "log", "--oneline", "-1")


def test_outils_externes_module_fonction(tmp_path: Path, depot: Path, capsys):
    module = tmp_path / "rag_factice.py"
    module.write_text(
        "from neoagent.tools import Tool\n"
        "def rag_tool(config_path=None):\n"
        "    return Tool('rechercher_doc', 'Recherche dans la documentation (RAG J05)',\n"
        "                {'type': 'object', 'properties': {'question': {'type': 'string'}}, 'required': ['question']},\n"
        "                lambda e: 'docs/adr/ADR-002.md:12: solde recalculé')\n")
    outils = charger_outils_externes(f"{module}:rag_tool")
    assert isinstance(outils[0], Tool) and outils[0].name == "rechercher_doc"
    code = main(["--repo", str(depot), "--tache", "x", "--offline", "--outils-externes", f"{module}:rag_tool"])
    assert code == 0


def test_outils_externes_invalides(depot: Path, capsys):
    assert main(["--repo", str(depot), "--tache", "x", "--offline", "--outils-externes", "sans_deux_points"]) == 2


def test_outils_externes_recoivent_la_configuration(tmp_path: Path):
    module = tmp_path / "mcp_factice.py"
    module.write_text(
        "from neoagent.tools import Tool\n"
        "def outils_mcp(config_path):\n"
        "    return [Tool('git_log', 'Historique (MCP git) depuis ' + str(config_path),\n"
        "                 {'type': 'object', 'properties': {}}, lambda e: 'a1b2c3 feat(conges)')]\n")
    outils = charger_outils_externes(f"{module}:outils_mcp", "labs/mcp/configs/mcp.json")
    assert outils[0].description.endswith("labs/mcp/configs/mcp.json")
