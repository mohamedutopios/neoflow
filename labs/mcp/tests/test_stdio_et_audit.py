"""Bout en bout en stdio, négociation « legacy » (celle d'OpenCode 1.19 par défaut) + journal d'audit."""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from commun.audit import masquer_arguments
from conftest import LAB, dernier_appel

ATTENDUS = {
    "retriever_server.py": {"search_code", "search_docs", "get_chunk"},
    "tickets_server.py": {"list_tickets", "get_ticket", "comment_ticket"},
    "readonly_sql_server.py": {"list_tables", "describe_table", "run_select", "demandes_par_statut"},
}
APPEL_LECTURE = {
    "retriever_server.py": ("search_docs", {"query": "pagination 0-based"}),
    "tickets_server.py": ("get_ticket", {"ticket_id": "NEO-123"}),
    "readonly_sql_server.py": ("run_select", {"sql": "SELECT count(*) AS n FROM demande"}),
}


async def _session(script: str):
    transport = StdioTransport(command=sys.executable, args=[str(LAB / script)], env=dict(os.environ), cwd=str(LAB))
    async with Client(transport, mode="legacy", timeout=30, init_timeout=60) as client:
        outils = await client.list_tools()
        outil, args = APPEL_LECTURE[script]
        res = await client.call_tool(outil, args, raise_on_error=False)
        return client.protocol_version, outils, res


@pytest.mark.parametrize("script", sorted(ATTENDUS))
def test_decouverte_et_lecture_en_stdio(script, journal):
    version, outils, res = asyncio.run(_session(script))
    assert version == "2025-11-25"                       # pas de handshake 2026-07-28 en mode legacy
    assert {o.name for o in outils} == ATTENDUS[script]
    for o in outils:
        assert o.input_schema["type"] == "object" and o.description
        lecture = o.annotations.read_only_hint
        assert lecture is (o.name != "comment_ticket")
    assert not res.is_error
    evenements = journal()
    types = [e["event"] for e in evenements]
    assert types[0] == "server_start" and "tools_list" in types and "tool_call" in types
    appel = [e for e in evenements if e["event"] == "tool_call"][-1]
    assert appel["actor"] == "svc-opencode-test" and appel["decision"] == "allowed"
    assert appel["result_sha256"] and appel["duration_ms"] >= 0


def test_ecriture_refusee_en_stdio_et_journalisee(journal):
    async def _run():
        transport = StdioTransport(command=sys.executable, args=[str(LAB / "tickets_server.py")],
                                   env=dict(os.environ), cwd=str(LAB))
        async with Client(transport, mode="legacy", timeout=30, init_timeout=60) as client:
            return await client.call_tool("comment_ticket", {"ticket_id": "NEO-142", "body": "Commentaire de test.",
                                                             "confirm": True}, raise_on_error=False)
    res = asyncio.run(_run())
    assert res.is_error and "lecture_seule" in res.content[0].text
    evt = dernier_appel(journal)
    assert (evt["tool"], evt["decision"], evt["reason"]) == ("comment_ticket", "refused", "lecture_seule")


def test_masquage_des_arguments():
    sortie = masquer_arguments({"body": "token=sk-ant-api03-ABCDEFGHIJKLMNOP", "court": "ok", "n": 3,  # gitleaks:allow (valeur factice de test)
                                "long": "x" * 400, "liste": ["a", "b"]})
    assert "sk-ant" not in json.dumps(sortie) and sortie["body"].startswith("[MASQUÉ: ")
    assert sortie["court"] == "ok" and sortie["n"] == 3
    assert sortie["long"].startswith("[400 car.; sha256:")
    assert sortie["liste"] == '["a", "b"]'
