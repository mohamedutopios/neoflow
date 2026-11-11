"""TP 1 — client Claude : requête à sortie structurée, gestion des arrêts, journal."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from neospec import schemas
from neospec.llm import ClientClaude, ClientSimule, Journal, RefusModele, SortieTronquee


class FluxFactice:
    def __init__(self, reponse):
        self.reponse = reponse

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.reponse


class SdkFactice:
    """Imite client.beta.messages.stream(**params) et mémorise les paramètres reçus."""

    def __init__(self, texte='{"ok": true}', stop_reason="end_turn"):
        self.params = None
        usage = SimpleNamespace(input_tokens=1200, output_tokens=300, cache_read_input_tokens=1000, cache_creation_input_tokens=0)
        self.reponse = SimpleNamespace(stop_reason=stop_reason, model="claude-opus-5-5", usage=usage, stop_details=None,
                                       content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=texte)])
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **params):
        self.params = params
        return FluxFactice(self.reponse)


def test_requete_sortie_structuree():
    sdk = SdkFactice()
    client = ClientClaude(client=sdk)
    assert client.json(etape="questions", systeme="SYS", message="MSG", schema=schemas.QUESTIONS_API) == {"ok": True}
    p = sdk.params
    assert p["model"] == "claude-opus-5-5"
    assert p["output_config"]["format"] == {"type": "json_schema", "schema": schemas.QUESTIONS_API}
    assert p["output_config"]["effort"] == "high"
    assert p["messages"] == [{"role": "user", "content": "MSG"}]
    assert p["system"][0]["text"] == "SYS" and p["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "temperature" not in p and "thinking" not in p


def test_modele_de_generation_et_repli():
    sdk = SdkFactice()
    ClientClaude(client=sdk).json(etape="generation", systeme="S", message="M", schema={"type": "object"})
    assert sdk.params["model"] == "claude-sonnet-5-5"
    assert sdk.params["fallbacks"] == "default"
    assert sdk.params["betas"] == ["server-side-fallback-2026-07-01"]
    sdk2 = SdkFactice()
    ClientClaude(client=sdk2, repli=False).json(etape="generation", systeme="S", message="M", schema={"type": "object"})
    assert "fallbacks" not in sdk2.params


@pytest.mark.parametrize("arret, exception", [("refusal", RefusModele), ("max_tokens", SortieTronquee)])
def test_arrets_non_nominaux(arret, exception):
    with pytest.raises(exception):
        ClientClaude(client=SdkFactice(stop_reason=arret)).json(etape="questions", systeme="S", message="M", schema={})


def test_journal_usage(tmp_path):
    journal = Journal(tmp_path / "j.jsonl")
    ClientClaude(client=SdkFactice(), journal=journal).json(etape="questions", systeme="S", message="M", schema={})
    ligne = json.loads((tmp_path / "j.jsonl").read_text().splitlines()[0])
    assert ligne["etape"] == "questions" and ligne["offline"] is False
    assert ligne["usage"]["cache_read_input_tokens"] == 1000


def test_client_simule_sans_reseau():
    client = ClientSimule("CONGES")
    sortie = client.json(etape="questions", systeme="S", message="M", schema={})
    assert len(sortie["questions"]) == 12
    generique = ClientSimule("MATERIEL_IT").json(etape="questions", systeme="S",
                                                   message="<ticket>Il faut que le catalogue soit rapide.</ticket>", schema={})
    assert generique["questions"][0]["id"] == "Q-01"
