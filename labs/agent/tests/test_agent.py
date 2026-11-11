from __future__ import annotations

import json
from pathlib import Path

from conftest import outil, texte

from neoagent import Agent, Approbateur, Journal, ModeleSimule, Politique, lire_journal, outils_de_base, usage_total
from neoagent.journal import CHAMPS, CLES_USAGE

PROD = "backend/src/main/java/com/neosoft/neoflow/conges/RegleConges.java"


def agent(depot: Path, tours, *, politique: Politique | None = None, **options) -> Agent:
    politique = politique or Politique.lecture(depot)
    return Agent(outils_de_base(depot, politique), offline=True, client=ModeleSimule(tours), **options)


def test_boucle_observation_decision_action(depot: Path, tmp_path: Path):
    journal = Journal(tmp_path / "traj.jsonl")
    a = agent(depot, [
        [texte("Je regarde la règle."), outil("chercher", {"motif": "dureeMax", "fichiers": "*.java"})],
        [outil("lire_fichier", {"chemin": PROD})],
        [texte("La durée maximale vaut 20 jours ouvrés (EF-06).")],
    ], journal=journal)

    r = a.executer("Où est la durée maximale ?")

    assert r.ok and r.statut == "termine" and r.etapes == 3
    assert r.reponse == "La durée maximale vaut 20 jours ouvrés (EF-06)."
    assert r.appels_outils == ["chercher", "lire_fichier"]
    # Le résultat de l'outil a bien été renvoyé au modèle, dans un message utilisateur, avec le bon tool_use_id.
    resultat = a.messages[2]["content"][0]
    assert resultat["type"] == "tool_result" and resultat["tool_use_id"] == a.messages[1]["content"][1]["id"]
    assert "RegleConges.java:4" in resultat["content"]
    types = [e["type"] for e in lire_journal(tmp_path / "traj.jsonl")]
    assert types == ["llm", "tool_call", "tool_result", "llm", "tool_call", "tool_result", "llm", "fin"]


def test_journal_respecte_le_contrat(depot: Path, tmp_path: Path):
    agent(depot, [[outil("lister", {})], [texte("fini")]], journal=Journal(tmp_path / "t.jsonl")).executer("liste")
    for evenement in lire_journal(tmp_path / "t.jsonl"):
        assert tuple(evenement) == CHAMPS
        if evenement["type"] in ("llm", "fin"):
            assert tuple(evenement["usage"]) == CLES_USAGE
            assert evenement["usage"]["cache_creation_input_tokens"] == 0  # hors ligne : aucune écriture en cache


def test_usage_total_compte_les_appels_pas_les_fins(depot: Path, tmp_path: Path):
    chemin = tmp_path / "gv.jsonl"
    a = agent(depot, [[texte("premier rapport")], [texte("second rapport")]], journal=Journal(chemin))
    premier = a.executer("tâche")
    second = a.poursuivre("le vérificateur est rouge")  # même session : deux lignes « fin », usage cumulé
    evenements = lire_journal(chemin)
    assert [e["type"] for e in evenements].count("fin") == 2
    assert usage_total(evenements) == second.usage != premier.usage
    assert usage_total([{"type": "llm", "usage": {"input_tokens": 7, "output_tokens": 1}}])["cache_creation_input_tokens"] == 0


def test_usage_cumule_et_cache_simule(depot: Path):
    r = agent(depot, [[outil("lister", {})], [outil("lister", {"chemin": "backend"})], [texte("ok")]]).executer("x")
    assert r.usage["output_tokens"] > 0 and r.usage["cache_read_input_tokens"] > 0
    assert r.tokens == sum(r.usage.values())


def test_ecriture_refusee_sans_approbation(depot: Path):
    a = agent(depot, [
        [outil("editer_fichier", {"chemin": PROD, "ancien": "return 20;", "nouveau": "return 21;"})],
        [texte("Écriture refusée : je m'arrête.")],
    ], politique=Politique.generateur(depot), approbateur=Approbateur("refus"))

    r = a.executer("Passe la durée à 21")

    assert r.ok and "return 20;" in (depot / PROD).read_text()
    resultat = a.messages[2]["content"][0]
    assert resultat["is_error"] and resultat["content"].startswith("REFUS HUMAIN")
    assert [e["entree"] for e in a.journal.evenements if e["type"] == "approbation"] == [{"accordee": False}]


def test_ecriture_accordee_puis_appliquee(depot: Path):
    reponses = iter(["o"])
    approbateur = Approbateur("interactif", entree=lambda _: next(reponses), sortie=lambda _: None)
    agent(depot, [
        [outil("editer_fichier", {"chemin": PROD, "ancien": "return 20;", "nouveau": "return 21;"})],
        [texte("Fait.")],
    ], politique=Politique.generateur(depot), approbateur=approbateur).executer("Passe la durée à 21")
    assert "return 21;" in (depot / PROD).read_text()


def test_lecture_jamais_soumise_a_approbation(depot: Path):
    a = agent(depot, [[outil("lister", {})], [texte("ok")]], approbateur=Approbateur("refus"))
    assert a.executer("liste").ok
    assert not [e for e in a.journal.evenements if e["type"] == "approbation"]


def test_refus_de_garde_fou_renvoye_au_modele(depot: Path):
    a = agent(depot, [
        [outil("executer_commande", {"commande": "rm -rf backend"})],
        [outil("editer_fichier", {"chemin": "../hors.txt", "nouveau": "x"})],
        [texte("Les deux actions sont refusées.")],
    ], politique=Politique.generateur(depot), approbateur=Approbateur("accord"))

    r = a.executer("nettoie")

    assert r.ok and (depot / "backend").exists() and not (depot.parent / "hors.txt").exists()
    erreurs = [e["sortie_extrait"] for e in a.journal.evenements if e["type"] == "erreur"]
    assert erreurs[0].startswith("garde-fou : commande hors allowlist")
    assert "hors du worktree" in erreurs[1]


def test_outil_inconnu(depot: Path):
    a = agent(depot, [[outil("supprimer_tout", {})], [texte("ok")]])
    a.executer("x")
    assert a.messages[2]["content"][0]["content"].startswith("outil inconnu")


def test_borne_nombre_d_etapes(depot: Path):
    tours = [[outil("lister", {"chemin": "backend", "profondeur": i % 7 + 1})] for i in range(10)]
    r = agent(depot, tours, max_etapes=4).executer("explore sans fin")
    assert r.statut == "etapes_max" and r.etapes == 4


def test_borne_budget_tokens(depot: Path):
    tours = [[outil("lire_fichier", {"chemin": PROD, "fin": i % 5 + 1})] for i in range(10)]
    r = agent(depot, tours, budget_tokens=2_000).executer("lis encore")
    assert r.statut == "budget_atteint" and r.tokens >= 2_000 and r.etapes < 10


def test_detection_de_boucle(depot: Path):
    meme = [outil("lire_fichier", {"chemin": PROD})]
    r = agent(depot, [meme, meme, meme, meme, [texte("jamais atteint")]]).executer("relis")
    assert r.statut == "boucle" and r.etapes == 3


def test_delai_global(depot: Path):
    r = agent(depot, [[outil("lister", {})]] * 5, timeout_s=0).executer("x")
    assert r.statut == "timeout"


def test_pause_turn_et_refus_du_modele(depot: Path):
    class Modele(ModeleSimule):
        def creer(self, systeme, messages, outils):
            reponse = super().creer(systeme, messages, outils)
            reponse.stop_reason = {1: "pause_turn", 2: "refusal"}.get(self.appels, reponse.stop_reason)
            return reponse

    a = Agent(outils_de_base(depot, Politique.lecture(depot)), offline=True,
              client=Modele([[texte("je réfléchis")], [texte("")]]))
    r = a.executer("x")
    assert r.statut == "refus_modele" and r.etapes == 2


def test_poursuivre_garde_l_historique_et_les_bornes(depot: Path):
    a = agent(depot, [[texte("premier")], [texte("second")]], max_etapes=5)
    a.executer("un")
    r = a.poursuivre("deux")
    assert r.reponse == "second" and r.etapes == 2 and len(a.messages) == 4


def test_explorateur_offline_par_defaut(depot: Path):
    a = Agent(outils_de_base(depot, Politique.lecture(depot)), offline=True)
    r = a.executer("Où est la méthode dureeMax de RegleConges ?")
    assert r.ok and r.appels_outils[:3] == ["lister", "chercher", "lire_fichier"]
    assert json.dumps(a.messages, default=str).count("toolu_sim_") >= 6
