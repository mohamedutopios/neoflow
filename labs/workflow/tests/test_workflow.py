"""Workflow LangGraph : exécution guidée, approbation, reprise, idempotence, retries, timeout, budget."""
from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

import workflow as wf
from config import charger
from llm import ErreurTransitoire
from memoire import StoreMemoire
from sources import Sources, router_heuristique, verifier_preuves

from conftest import LAB

Q_SYMBOLE = "Où est calculé le niveau de validation dans CircuitValidationService ?"
Q_HORS_SUJET = "Quelle est la politique de rétention des sauvegardes Kubernetes du cluster ?"
CIRCUIT = "backend/src/main/java/com/neosoft/neoflow/validation/CircuitValidationService.java"


def cfg_test(**surcharges) -> dict:
    cfg = charger()
    cfg["retries"].update({"intervalle_initial_s": 0.01, "jitter": False})
    cfg["rag"]["activer"] = "non"
    for chemin, valeur in surcharges.items():
        bloc, cle = chemin.split("__")
        cfg[bloc][cle] = valeur
    return cfg


def session(depot, etat, cfg=None, **kw) -> wf.Session:
    return wf.ouvrir_session(offline=True, etat=str(etat), depot=str(depot.racine), cfg=cfg or cfg_test(), **kw)


def lancer(s: wf.Session, thread: str, question: str = Q_SYMBOLE, ticket: str | None = "NF-402"):
    return s.invoquer({"question": question, "ticket": ticket, "demandeur": "alice",
                       "portee": "projet:neoflow"}, thread)


def approuver(s: wf.Session, thread: str, **reponse):
    return s.invoquer(Command(resume={"decision": "approuver", "approbateur": "bob", **reponse}), thread)


# ---------------------------------------------------------------- exécution guidée et approbation
def test_execution_guidee_suspendue_avant_toute_action(depot, etat):
    s = session(depot, etat)
    lancer(s, "t1")
    snap = s.instantane("t1")
    assert snap.next == ("approbation",)
    assert snap.values["routage"][0]["source"] == "symboles"          # sélection d'outil
    assert any(p["path"] == CIRCUIT for p in snap.values["preuves"])   # récupération
    attente = s.en_attente("t1")
    assert attente["action"]["type"] == "commenter_ticket"
    assert s.ctx.effets.commentaires("NF-402") == []                  # rien d'exécuté sans accord

    approuver(s, "t1")
    v = s.instantane("t1").values
    assert v["statut"] == "termine"
    assert len(s.ctx.effets.commentaires("NF-402")) == 1
    assert [l for l in s.ctx.journal.lire("t1") if l["type"] == "cloture"][0]["statut"] == "termine"


def test_refus_humain_aucun_effet(depot, etat):
    s = session(depot, etat)
    lancer(s, "t1")
    s.invoquer(Command(resume={"decision": "refuser", "approbateur": "bob"}), "t1")
    assert s.instantane("t1").values["statut"] == "refuse"
    assert s.ctx.effets.commentaires("NF-402") == []


@pytest.mark.parametrize("reponse", ["ok", {"decision": "approuver", "approbateur": "alice"},
                                     {"decision": "approuver", "approbateur": "agent:workflow"},
                                     {"decision": "valider", "approbateur": "bob"},
                                     {"decision": "modifier", "approbateur": "bob", "contenu": " "}])
def test_reponse_d_approbation_invalide_vaut_refus(depot, etat, reponse):
    s = session(depot, etat)
    lancer(s, "t1")
    s.invoquer(Command(resume=reponse), "t1")
    assert s.instantane("t1").values["approbation"]["decision"] == "refuser"
    assert s.ctx.effets.commentaires("NF-402") == []


def test_modification_humaine_executee_telle_quelle(depot, etat):
    s = session(depot, etat)
    lancer(s, "t1")
    approuver(s, "t1", decision="modifier", contenu="Voir CircuitValidationService.calculerNiveau.")
    (c,) = s.ctx.effets.commentaires("NF-402")
    assert c["contenu"] == "Voir CircuitValidationService.calculerNiveau."


def test_action_alteree_apres_approbation_bloquee(depot, etat):
    """Défense en profondeur : même un état patché ne permet pas d'exécuter sans approbation valide."""
    s = session(depot, etat)
    lancer(s, "t1")
    s.graphe.update_state(s.config("t1"), {"approbation": {"decision": "approuver", "approbateur": "bob",
                                                           "empreinte": "falsifiee"}}, as_node="approbation")
    assert s.instantane("t1").next == ("executer_action",)
    s.invoquer(None, "t1")
    v = s.instantane("t1").values
    assert v["statut"] == "bloque" and v["resultat_action"]["motif"] == "action modifiée après approbation"
    assert s.ctx.effets.commentaires("NF-402") == []


def test_reprendre_ne_vaut_pas_approbation(depot, etat):
    s = session(depot, etat)
    lancer(s, "t1")
    s.invoquer(None, "t1")  # reprise naïve sans Command(resume=...)
    assert s.instantane("t1").next == ("approbation",)
    assert s.ctx.effets.commentaires("NF-402") == []


def test_question_sans_ticket_pas_d_approbation(depot, etat):
    s = session(depot, etat)
    lancer(s, "t1", ticket=None)
    v = s.instantane("t1").values
    assert v["statut"] == "termine" and v["proposition"]["action"]["type"] == "aucune"
    assert v.get("approbation") is None


# ---------------------------------------------------------------- crash, reprise, idempotence
def cli(depot, etat, *args, check_rc=None):
    env = {**os.environ, "NEOFLOW_RAG": "off", "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run([sys.executable, str(LAB / "workflow.py"), *args, "--offline", "--etat", str(etat),
                           "--depot", str(depot.racine)], capture_output=True, text=True, env=env, timeout=120)
    if check_rc is not None:
        assert proc.returncode == check_rc, proc.stdout + proc.stderr
    return proc


def test_crash_apres_effet_puis_reprise_sans_double_execution(depot, etat):
    cli(depot, etat, "lancer", "--thread", "t1", "--ticket", "NF-402", "--demandeur", "alice",
        "--question", Q_SYMBOLE, check_rc=0)
    p = cli(depot, etat, "approuver", "--thread", "t1", "--approbateur", "bob", "--crash-apres-effet", check_rc=137)
    assert "crash simulé" in p.stdout
    s = session(depot, etat)
    assert len(s.ctx.effets.commentaires("NF-402")) == 1             # l'effet a eu lieu
    assert s.instantane("t1").next == ("executer_action",)            # mais le nœud n'est pas checkpointé
    s.fermer()

    p = cli(depot, etat, "reprendre", "--thread", "t1", check_rc=0)
    assert "reprise depuis le checkpoint" in p.stdout
    s = session(depot, etat)
    assert s.instantane("t1").values["statut"] == "termine"
    assert len(s.ctx.effets.commentaires("NF-402")) == 1             # PAS de double exécution
    evts = [l["message"] for l in s.ctx.journal.lire("t1") if l.get("noeud") == "executer_action"]
    assert evts.count("début du nœud") == 2                             # le nœud a bien été rejoué
    assert sum("déjà appliqué" in e for e in evts) == 1


def test_sans_idempotence_la_reprise_duplique_l_effet(depot, etat):
    cli(depot, etat, "lancer", "--thread", "t1", "--ticket", "NF-402", "--demandeur", "alice",
        "--question", Q_SYMBOLE, check_rc=0)
    cli(depot, etat, "approuver", "--thread", "t1", "--approbateur", "bob", "--crash-apres-effet",
        "--sans-idempotence", check_rc=137)
    cli(depot, etat, "reprendre", "--thread", "t1", "--sans-idempotence", check_rc=0)
    s = session(depot, etat)
    assert len(s.ctx.effets.commentaires("NF-402")) == 2              # le problème que l'on veut éviter


def test_lancer_un_thread_existant_est_refuse(depot, etat):
    cli(depot, etat, "lancer", "--thread", "t1", "--question", Q_SYMBOLE, check_rc=0)
    p = cli(depot, etat, "lancer", "--thread", "t1", "--question", Q_SYMBOLE, check_rc=2)
    assert "existe déjà" in p.stdout


def test_rejouer_depuis_un_checkpoint_ne_duplique_pas(depot, etat):
    s = session(depot, etat)
    lancer(s, "t1")
    approuver(s, "t1")
    cp = next(h for h in s.graphe.get_state_history(s.config("t1")) if h.next == ("executer_action",))
    s.invoquer(None, "t1", cp.config["configurable"]["checkpoint_id"])   # time travel (fork)
    assert len(s.ctx.effets.commentaires("NF-402")) == 1


def test_annuler_applique_la_compensation_une_seule_fois(depot, etat):
    s = session(depot, etat)
    lancer(s, "t1")
    approuver(s, "t1")
    assert len(s.ctx.effets.compenser("t1")) == 1
    assert s.ctx.effets.commentaires("NF-402") == []
    assert s.ctx.effets.compenser("t1") == []


# ---------------------------------------------------------------- tentatives bornées, timeout, budget
def test_panne_transitoire_absorbee_par_les_retries(depot, etat):
    s = session(depot, etat, panne=2)
    lancer(s, "t1", ticket=None)
    assert s.instantane("t1").values["statut"] == "termine"
    assert s.ctx.sources.appels == 3


def test_retries_bornes_puis_reprise_apres_erreur(depot, etat):
    s = session(depot, etat, panne=10)
    with pytest.raises(ErreurTransitoire):
        lancer(s, "t1", ticket=None)
    assert s.ctx.sources.appels == 3                                    # borné : max_tentatives
    assert s.instantane("t1").next == ("rechercher",)                   # checkpoint conservé
    s.fermer()
    s2 = session(depot, etat)                                           # « panne corrigée », nouveau processus
    s2.invoquer(None, "t1")
    v = s2.instantane("t1").values
    assert v["statut"] == "termine"
    assert v["sources_essayees"] == ["symboles"]                        # router_source non rejoué


def test_timeout_de_source_borne_la_duree(depot, etat):
    cfg = cfg_test(limites__timeout_source_s=0.2)
    s = session(depot, etat, cfg=cfg, lenteur_s=1.5)
    t0 = time.monotonic()
    with pytest.raises(ErreurTransitoire, match="timeout"):
        lancer(s, "t1", ticket=None)
    assert time.monotonic() - t0 < 3.0                                  # 3 x 0,2 s, pas 3 x 1,5 s
    assert s.ctx.sources.appels == 3


def test_recursion_limit_filet_de_securite(depot, etat):
    s = session(depot, etat, cfg=cfg_test(limites__recursion_limit=6))
    with pytest.raises(GraphRecursionError):
        lancer(s, "t1", question=Q_HORS_SUJET, ticket=None)


def test_preuves_insuffisantes_relances_bornees_puis_escalade(depot, etat):
    s = session(depot, etat)
    lancer(s, "t1", question=Q_HORS_SUJET, ticket="NF-402")
    v = s.instantane("t1").values
    assert v["statut"] == "escalade"
    assert len(v["sources_essayees"]) == 1 + s.ctx.cfg["limites"]["max_relances"]
    assert v.get("proposition") is None and s.ctx.effets.commentaires("NF-402") == []


def test_budget_llm_epuise_escalade_sans_appel(depot, etat):
    s = session(depot, etat, cfg=cfg_test(budget__appels_llm=0))
    lancer(s, "t1")
    v = s.instantane("t1").values
    assert v["statut"] == "escalade" and "budget" in v["motif_fin"]
    assert v["consommation"]["appels_llm"] == 0


# ---------------------------------------------------------------- routage, fraîcheur, mémoire
@pytest.mark.parametrize("question,attendu", [
    ("Où est défini CircuitValidationService ?", "symboles"),
    ("Que fait determinerNiveau() ?", "symboles"),
    ("Quand le calcul du niveau a-t-il changé ? Qui a introduit la règle DSI ?", "git"),
    ("Que dit l'ADR sur le circuit de validation ?", "documents"),
    ("D'où vient le message \"Transition invalide\" ?", "lexical"),
    ("Où est lue la clé neoflow.notification.api-key ?", "lexical"),
    ("Comment fonctionne le circuit de validation ?", None),
    ("Que renvoie calculerNiveau quand le montant est nul ?", "symboles"),        # « quand » conditionnel
    ("Quelle est la classe qui a la responsabilité du calcul ?", None),          # « qui a » non historique
    ("Depuis quand la règle DSI existe-t-elle ?", "git"),
    ("Comment une nuitée d'hôtel est-elle plafonnée à l'étranger ?", None),     # apostrophes : pas une citation
    ("D'où vient le message « Transition interdite » ?", "lexical"),
])
def test_routage_heuristique(question, attendu):
    assert router_heuristique(question)[0] == attendu


def test_preuve_indexee_a_un_commit_perime_est_ecartee(depot, etat):
    c1 = depot.git("rev-parse", "HEAD")
    depot.ecrire(CIRCUIT, depot.lire(CIRCUIT).replace("0.0", "BigDecimal.ZERO.doubleValue()"))
    depot.commit("refactor: montant nul")
    preuves = [{"path": CIRCUIT, "start_line": 10, "end_line": 15, "commit": c1, "text": "calculerNiveau niveau"},
               {"path": "docs/adr/ADR-001-circuit-validation.md", "start_line": 1, "end_line": 8, "commit": c1,
                "text": "niveau de validation"}]
    v = verifier_preuves("niveau de validation", preuves, depot.racine, "hybride", cfg_test())
    assert [p["path"] for p in v["obsoletes"]] == [CIRCUIT]
    assert [p["path"] for p in v["fraiches"]] == ["docs/adr/ADR-001-circuit-validation.md"]


def test_memoire_obsolete_ecartee_du_contexte_du_workflow(depot, etat):
    store = StoreMemoire(etat / "memoire.db", cfg_test())
    m = store.ajouter("semantique", "Le niveau de validation est calculé par RegleValidationLegacy via "
                      "CircuitValidationService, montant nul converti en 0.0", "projet:neoflow",
                      source=f"{CIRCUIT}@HEAD:11-13", depot=depot.racine)
    depot.ecrire(CIRCUIT, depot.lire(CIRCUIT).replace(
        "Double montant = d.getMontant() != null ? d.getMontant().doubleValue() : 0.0;",
        "double montant = MontantUtils.versDouble(d.getMontant());"))
    depot.commit("refactor: conversion du montant")
    s = session(depot, etat)
    lancer(s, "t1", ticket=None)
    v = s.instantane("t1").values
    assert m.id in [e["id"] for e in v["memoires_ecartees"]]
    assert m.id not in [e["id"] for e in v["memoires"]]
    assert store.get(m.id).statut == "invalide"


def test_rag_absent_degrade_vers_recherche_locale(depot):
    cfg = cfg_test()
    cfg["rag"].update({"activer": "auto", "chemin_lab": "../inexistant"})
    src = Sources(depot.racine, cfg)
    assert src.searcher is None and "absent" in src.etat_rag
    res = src.rechercher("vectoriel", "circuit de validation niveau")
    assert res and src.degradations and "BM25 local" in src.degradations[0]


def test_preuve_marquee_stale_par_le_lab_rag_est_ecartee(depot):
    head = depot.git("rev-parse", "HEAD")
    preuves = [{"path": CIRCUIT, "start_line": 10, "end_line": 15, "commit": head[:7], "stale": True,
                "text": "niveau validation"},
               {"path": CIRCUIT, "start_line": 1, "end_line": 9, "commit": head[:7] + "+dirty", "stale": False,
                "text": "niveau validation"}]
    v = verifier_preuves("niveau de validation", preuves, depot.racine, "hybride", cfg_test())
    assert len(v["obsoletes"]) == 1 and "stale" in v["obsoletes"][0]["motif"]
    assert len(v["fraiches"]) == 1                      # SHA court + « +dirty » reconnus


def test_glossaire_metier_etend_la_requete_et_la_couverture(depot):
    from sources import couverture, etendre_requete
    g = {"arrondi": ["Math.round"], "ramené": ["Math.round"]}
    assert etendre_requete("pourquoi le montant est ramené à l'euro", g).endswith("Math.round")
    preuve = [{"path": "Calcul.java", "text": "rembourse = Math.round(rembourse * 100) / 100;"}]
    assert couverture("montant ramené", preuve) < couverture("montant ramené", preuve, glossaire=g)


def test_couverture_mesuree_sur_le_sujet_de_la_question():
    from sources import couverture
    preuve = [{"path": "CircuitValidationService.java", "text": "public int calculerNiveau(Demande d)"}]
    assert couverture("Où est défini CircuitValidationService et qui l'appelle ?", preuve) == 1.0
    assert couverture("Où est défini RegleInexistante ?", preuve) == 0.0
