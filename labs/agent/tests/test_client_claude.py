"""ClientClaude testé avec un faux SDK : on vérifie la requête construite, jamais d'appel réseau."""

from __future__ import annotations

from types import SimpleNamespace

from neoagent import Agent, Journal, Politique, lire_journal, outils_de_base
from neoagent.modele import BETA_REPLI, ClientClaude


class FauxSDK:
    def __init__(self):
        self.appels: list[dict] = []
        reponse = SimpleNamespace(
            content=[SimpleNamespace(type="thinking", thinking="", signature="sig"),
                     SimpleNamespace(type="text", text="Je lis le fichier."),
                     SimpleNamespace(type="tool_use", id="toolu_1", name="lire_fichier", input={"chemin": "pom.xml"})],
            stop_reason="tool_use", model="claude-sonnet-5-5",
            usage=SimpleNamespace(input_tokens=120, output_tokens=40, cache_read_input_tokens=900,
                                  cache_creation_input_tokens=2500))
        creer = lambda **kw: self.appels.append(kw) or reponse  # noqa: E731
        self.messages = SimpleNamespace(create=creer)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=creer))


def test_requete_avec_repli_cache_et_effort():
    sdk = FauxSDK()
    r = ClientClaude("claude-sonnet-5-5", client=sdk).creer("système", [{"role": "user", "content": "x"}],
                                                            [{"name": "lire_fichier"}])
    appel = sdk.appels[0]
    assert appel["model"] == "claude-sonnet-5-5" and appel["max_tokens"] == 16_000
    assert appel["betas"] == [BETA_REPLI] and appel["fallbacks"] == "default"
    assert appel["cache_control"] == {"type": "ephemeral"} and appel["output_config"] == {"effort": "medium"}
    assert "tool_choice" not in appel  # pas d'appel forcé : refusé (400) par Claude Sonnet 5.5
    assert r.stop_reason == "tool_use" and r.appels[0]["name"] == "lire_fichier" and r.texte == "Je lis le fichier."
    assert len(r.brut) == 3  # le bloc de réflexion revient tel quel dans l'historique
    assert r.usage["cache_read_input_tokens"] == 900 and r.usage["cache_creation_input_tokens"] == 2500


def test_modele_sans_repli_serveur():
    sdk = FauxSDK()
    ClientClaude("claude-haiku-5-5", client=sdk, effort=None).creer("s", [], [])
    appel = sdk.appels[0]
    assert "betas" not in appel and "fallbacks" not in appel and "output_config" not in appel
    assert appel["cache_control"] == {"type": "ephemeral"}


def test_usage_complet_dans_le_journal(tmp_path):
    """Les quatre compteurs de response.usage, dont l'écriture en cache, arrivent dans le journal (J10 : coûts)."""
    sdk = FauxSDK()
    fin = SimpleNamespace(content=[SimpleNamespace(type="text", text="fini")], stop_reason="end_turn",
                          model="claude-sonnet-5-5",
                          usage=SimpleNamespace(input_tokens=30, output_tokens=5, cache_read_input_tokens=3400,
                                                cache_creation_input_tokens=0))
    reponses = iter([None, fin])
    premiere = sdk.beta.messages.create
    sdk.beta.messages.create = lambda **kw: next(reponses) or premiere(**kw)
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    chemin = tmp_path / "traj.jsonl"
    r = Agent(outils_de_base(tmp_path, Politique.lecture(tmp_path)), client=ClientClaude("claude-sonnet-5-5", client=sdk),
              journal=Journal(chemin)).executer("lis pom.xml")
    evenements = lire_journal(chemin)
    llm = [e for e in evenements if e["type"] == "llm"]
    assert llm[0]["usage"] == {"input_tokens": 120, "output_tokens": 40, "cache_read_input_tokens": 900,
                               "cache_creation_input_tokens": 2500}
    assert evenements[-1]["type"] == "fin" and evenements[-1]["usage"] == r.usage == {
        "input_tokens": 150, "output_tokens": 45, "cache_read_input_tokens": 4300, "cache_creation_input_tokens": 2500}
