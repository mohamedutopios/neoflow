"""Intégration avec l'agent du J4 : `neoagent --outils-externes labs/mcp/neoagent_outils.py:outils_mcp`.

Le CLI neoagent tourne dans un sous-processus (son propre `neoagent`), en --offline avec un scénario simulé :
aucun appel à l'API Claude. Ignoré si l'agent du J4 n'est pas complet (boucle encore en TODO) ; pour le
tester avec le corrigé du J4 : NEOFLOW_TEST_NEOAGENT_DIR=<.../J04_agent_dev_patterns/solutions/labs/agent>.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import LAB

DIR_AGENT = Path(os.environ.get("NEOFLOW_TEST_NEOAGENT_DIR") or LAB.parent / "agent")


def _agent_complet() -> bool:
    agent = DIR_AGENT / "neoagent" / "agent.py"
    return agent.is_file() and "NotImplementedError(\"TODO-J04 boucle" not in agent.read_text(encoding="utf-8")


pytestmark = pytest.mark.skipif(not _agent_complet(), reason="neoagent (J4) absent ou boucle encore en TODO")


def _config(tmp: Path, depot: Path) -> Path:
    env = {"NEOFLOW_REPO": str(depot), "NEOFLOW_MCP_AUDIT": str(tmp / "audit.jsonl"), "NEOFLOW_MCP_ACTOR": "svc-neoagent-test",
           "NEOFLOW_RAG_MODE": "lexical", "NEOFLOW_TICKETS_WRITE": "on", "NEOFLOW_TICKETS_STATE": str(tmp / "etat.json"),
           "NEOFLOW_DB_URL": f"sqlite:///{tmp / 'demo.db'}"}
    py = sys.executable
    cfg = {"racine": str(LAB), "journal": str(tmp / "client.jsonl"), "serveurs": {
        "rag": {"commande": [py, str(LAB / "retriever_server.py")], "env": env,
                "outils": {"search_code": "lecture", "get_chunk": "lecture"}},
        "tickets": {"commande": [py, str(LAB / "tickets_server.py")], "env": env,
                    "outils": {"get_ticket": "lecture",
                               "comment_ticket": {"risque": "ecriture", "parametre_confirmation": "confirm"}}},
        "db": {"commande": [py, str(LAB / "readonly_sql_server.py")], "env": env, "outils": {"run_select": "lecture"}},
    }}
    chemin = tmp / "mcp_client.json"
    chemin.write_text(json.dumps(cfg), encoding="utf-8")
    return chemin


def _neoagent(depot: Path, tmp: Path, approbation: str) -> list[dict]:
    journal = tmp / f"traj-{approbation}.jsonl"
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(DIR_AGENT), str(LAB)]))
    res = subprocess.run([sys.executable, "-m", "neoagent.cli", "--repo", str(depot), "--offline",
                          "--tache", "Instruis le ticket NEO-131 avec les outils MCP.",
                          "--script", str(LAB / "scenarios" / "neoagent_neo131.json"),
                          "--outils-externes", f"{LAB / 'neoagent_outils.py'}:outils_mcp",
                          "--outils-config", str(_config(tmp, depot)),
                          "--approbation", approbation, "--journal", str(journal)],
                         capture_output=True, text=True, timeout=180, env=env, cwd=str(depot))
    assert journal.exists(), res.stderr[-2000:]
    return [json.loads(l) for l in journal.read_text(encoding="utf-8").splitlines()]


def test_neoagent_approbation_accordee_ecrit_une_fois(depot, tmp_path):
    traj = _neoagent(depot, tmp_path, "accord")
    appels = [e["outil"] for e in traj if e["type"] == "tool_call"]
    assert appels[:2] == ["tickets_get_ticket", "git_git_log"] or "tickets_get_ticket" in appels
    assert [e for e in traj if e["type"] == "approbation" and e["outil"] == "tickets_comment_ticket"]
    etat = json.loads((tmp_path / "etat.json").read_text(encoding="utf-8"))
    assert [c["auteur"] for c in etat["commentaires"]] == ["svc-neoagent-test"]
    client = [json.loads(l) for l in (tmp_path / "client.jsonl").read_text(encoding="utf-8").splitlines()]
    ecriture = [e for e in client if e.get("outil") == "tickets_comment_ticket"][-1]
    assert ecriture["confirme_par"] == "hote" and ecriture["decision"] == "execute"
    refus = [e for e in traj if e["type"] == "tool_result" and e["outil"] == "db_run_select"]
    assert "table_non_autorisee" in json.dumps(refus, ensure_ascii=False)


def test_neoagent_approbation_refusee_n_ecrit_rien(depot, tmp_path):
    traj = _neoagent(depot, tmp_path, "refus")
    resultat = [e for e in traj if e["type"] == "tool_result" and e["outil"] == "tickets_comment_ticket"]
    assert "REFUS HUMAIN" in json.dumps(resultat, ensure_ascii=False)
    assert not (tmp_path / "etat.json").exists()
