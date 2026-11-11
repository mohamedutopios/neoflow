"""Option Java : le serveur MCP tickets écrit avec le SDK MCP Java, consommé par le client Python (pont -> Tool).

Ignoré si le jar n'est pas construit : cd labs/mcp/java/tickets-server && ./mvnw -q package
(ou NEOFLOW_TEST_JAVA_JAR=<chemin du jar>).
"""
from __future__ import annotations

import json
import os
import shutil

import pytest

from client import PolitiqueMCP, outils_mcp
from conftest import LAB

JAR = os.environ.get("NEOFLOW_TEST_JAVA_JAR") or str(LAB / "java" / "tickets-server" / "target" / "neoflow-mcp-tickets.jar")
pytestmark = pytest.mark.skipif(not (os.path.isfile(JAR) and shutil.which("java")),
                                reason="jar Java non construit (./mvnw package) ou java absent")


def test_serveur_java_branche_sur_le_pont(tmp_path):
    cfg = tmp_path / "mcp_client.json"
    cfg.write_text(json.dumps({"racine": str(LAB), "journal": str(tmp_path / "client.jsonl"), "serveurs": {
        "tickets-java": {"commande": ["java", "-jar", JAR], "env_hote": ["PATH", "HOME", "JAVA_HOME"],
                         "env": {"NEOFLOW_TICKETS_DATA": str(LAB / "data" / "tickets.json")},
                         "outils": {"list_tickets": "lecture", "get_ticket": "lecture"}}}}), encoding="utf-8")
    politique = PolitiqueMCP()
    try:
        outils = {o.name: o for o in outils_mcp(cfg, politique)}
        assert set(outils) == {"tickets_java_list_tickets", "tickets_java_get_ticket"}
        sortie = outils["tickets_java_get_ticket"].handler({"ticket_id": "NEO-142"})
        assert 'confiance="non_fiable"' in sortie and "commentaire_cache_pour_ia" in sortie
        refus = outils["tickets_java_get_ticket"].handler({"ticket_id": "../etc/passwd"})
        assert "arguments_invalides" in refus                     # validé par le client avant l'envoi
        assert '"count":1' in outils["tickets_java_list_tickets"].handler({"statut": "EN_COURS", "limit": 5})
    finally:
        politique.gestionnaire.fermer()
