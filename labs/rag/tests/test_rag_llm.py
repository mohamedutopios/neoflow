"""Fournisseurs de génération : offline déterministe, client compatible OpenAI simulé. Aucun appel réseau."""
import types

import pytest

import rag_llm
from rag_common import load_config

HITS = [{"citation": "backend/A.java:1-5@abc1234", "symbol": "A.calculerNiveau", "kind": "method",
         "text": "/** Niveau de validation calculé à la soumission. */\npublic int calculerNiveau() { return 2; }"},
        {"citation": "docs/x.md:1-3@abc1234", "symbol": "Doc", "kind": "section", "text": "Rien à voir ici, parking."}]


def test_reponse_offline_extractive_et_citee():
    gen = rag_llm.repondre("Où est calculé le niveau de validation ?", HITS, "offline", load_config())
    assert gen.fournisseur == "offline" and "[P1]" in gen.texte and gen.input_tokens == 0
    assert gen.texte == rag_llm.repondre("Où est calculé le niveau de validation ?", HITS, "offline", load_config()).texte


def test_juge_offline():
    verdict, _ = rag_llm.juger("Le niveau de validation est calculé à la soumission [P1].\nLe ciel est vert [P2].",
                               HITS, "offline", load_config())
    assert [c["supported"] for c in verdict["claims"]] == [True, False]


def test_information_absente():
    assert rag_llm.repondre("Quelle est la couleur du logo ?", HITS[1:], "offline", load_config()).texte \
        == "Information absente des passages."


def test_fournisseur_non_declare():
    with pytest.raises(ValueError):
        rag_llm.repondre("q ?", HITS, "inconnu", load_config())


def test_client_compatible_openai_simule(monkeypatch):
    appels = {}

    class FauxClient:
        def __init__(self, base_url, api_key, timeout):
            appels.update(base_url=base_url, api_key=api_key)
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

        def create(self, **kw):
            appels.update(kw)
            message = types.SimpleNamespace(content="Réponse [P1].")
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)],
                                         usage=types.SimpleNamespace(prompt_tokens=120, completion_tokens=8))

    import openai
    monkeypatch.setattr(openai, "OpenAI", FauxClient)
    monkeypatch.setenv("NEOGEN_API_KEY", "cle-de-test")
    gen = rag_llm.repondre("q ?", HITS, "neogen", load_config())
    assert appels["base_url"].endswith("/v1") and appels["api_key"] == "cle-de-test"
    assert appels["model"] == "qwen3-coder" and appels["temperature"] == 0
    assert gen.texte == "Réponse [P1]." and (gen.input_tokens, gen.output_tokens) == (120, 8)
