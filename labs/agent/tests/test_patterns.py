from __future__ import annotations

import threading
from pathlib import Path

import pytest
from conftest import git, outil, texte

from neoagent import Agent, Approbateur, ModeleSimule, Politique, outils_de_base
from neoagent.patterns import (SousTache, classer, evaluateur_tracabilite, evaluator_optimizer, extraire_plan,
                               generator_verifier, orchestrer, plan_execute, react, router)
from neoagent.patterns.orchestrator_workers import synthese
from neoagent.patterns.routing import classifieur_llm
from neoagent.verificateurs import Verdict, VerificateurCommande, tous

PROD = "backend/src/main/java/com/neosoft/neoflow/conges/RegleConges.java"


def agent(racine: Path, tours, politique: Politique | None = None, approbation: str = "accord") -> Agent:
    politique = politique or Politique.generateur(racine)
    return Agent(outils_de_base(racine, politique), offline=True, client=ModeleSimule(tours),
                 approbateur=Approbateur(approbation))


def test_react_est_la_boucle_native(depot: Path):
    assert react(agent(depot, [[texte("rien à faire")]]), "x").ok


@pytest.mark.parametrize("tache,route", [
    ("Relis le diff de la branche feat/conges", "revue"),
    ("Écris les tests JUnit de EF-07", "tests"),
    ("Où est calculé le niveau de validation ?", "exploration"),
    ("Implémente la tâche T07 RegleConges", "implementation"),
])
def test_routing_deterministe(tache: str, route: str):
    assert classer(tache) == route


def test_router_appelle_la_route_et_repli_par_defaut(depot: Path):
    appelees: list[str] = []
    routes = {"implementation": lambda t: appelees.append(t) or agent(depot, [[texte("fait")]]).executer(t)}
    etiquette, resultat = router("Relis le diff", routes)
    assert etiquette == "revue" and resultat.ok and appelees == ["Relis le diff"]


def test_classifieur_llm_leger_et_repli():
    classer_llm = classifieur_llm(ModeleSimule([[texte("tests")], [texte("poème")]]), ("tests", "revue", "implementation"))
    assert classer_llm("ajoute des preuves") == "tests"
    assert classer_llm("autre chose") == "implementation"


def test_extraire_plan():
    plan = extraire_plan('Voici le plan.\n[{"etape": "T04 calendrier", "fichiers": ["conges/CalendrierConges.java"], '
                         '"verification": "./mvnw -q test -Dtest=CalendrierCongesTest"}]')
    assert plan[0].etape == "T04 calendrier" and plan[0].fichiers == ["conges/CalendrierConges.java"]
    with pytest.raises(ValueError):
        extraire_plan("pas de plan")


def test_plan_execute_plan_valide_puis_etapes_isolees(depot: Path):
    planificateur = agent(depot, [[outil("lister", {})], [texte(
        'Plan :\n[{"etape": "Remplacer 20 par la constante", "fichiers": ["' + PROD + '"]},'
        ' {"etape": "Vérifier", "fichiers": []}]')]], Politique.lecture(depot))
    executants = iter([
        agent(depot, [[outil("editer_fichier", {"chemin": PROD, "ancien": "return 20;", "nouveau": "return MAX;"})],
                      [texte("étape 1 faite")]]),
        agent(depot, [[outil("git_diff", {})], [texte("étape 2 faite")]]),
    ])
    r = plan_execute(planificateur, lambda: next(executants), "Introduire une constante", Approbateur("accord"))
    assert r.statut == "termine" and [x.reponse for x in r.resultats] == ["étape 1 faite", "étape 2 faite"]
    assert "return MAX;" in (depot / PROD).read_text()


def test_plan_execute_plan_refuse_par_l_humain(depot: Path):
    planificateur = agent(depot, [[texte('[{"etape": "tout réécrire"}]')]], Politique.lecture(depot))
    r = plan_execute(planificateur, lambda: pytest.fail("aucune exécution sans plan validé"), "x", Approbateur("refus"))
    assert r.statut == "plan_refuse"
    decision = [e for e in planificateur.journal.evenements if e["type"] == "approbation"]
    assert decision and decision[0]["outil"] == "plan_execute" and decision[0]["entree"]["accordee"] is False


def test_generator_verifier_corrige_apres_retour_du_verificateur(depot: Path):
    verdicts = iter([Verdict(False, "./mvnw -q test", 1, "Tests run: 3, Failures: 1\nexpected: 20 but was: 21", 0.1),
                     Verdict(True, "./mvnw -q test", 0, "BUILD SUCCESS", 0.1)])
    generateur = agent(depot, [
        [outil("editer_fichier", {"chemin": PROD, "ancien": "return 20;", "nouveau": "return 21;"})],
        [texte("Fait, tous les tests passent.")],                       # le générateur se trompe… et l'affirme
        [outil("editer_fichier", {"chemin": PROD, "ancien": "return 21;", "nouveau": "return 20;"})],
        [texte("Corrigé : 20 jours ouvrés au plus (EF-06).")],
    ])

    r = generator_verifier(generateur, "Tâche T07", lambda _: next(verdicts), depot)

    assert r.ok and r.tours == 2 and [v.ok for v in r.verdicts] == [False, True]
    retour = generateur.messages[4]["content"]
    assert "ROUGE" in retour and "expected: 20 but was: 21" in retour and "Ne modifiez" in retour


def test_generator_verifier_s_arrete_apres_max_tours(depot: Path):
    rouge = Verdict(False, "./mvnw -q test", 1, "FAIL", 0.1)
    r = generator_verifier(agent(depot, [[texte("essai")]] * 5), "x", lambda _: rouge, depot, max_tours=3)
    assert r.statut == "echec_verification" and r.tours == 3 and len(r.verdicts) == 3


def test_generator_verifier_ne_verifie_pas_un_generateur_arrete(depot: Path):
    a = agent(depot, [[outil("lister", {"profondeur": i + 1})] for i in range(9)])
    a.max_etapes = 2
    r = generator_verifier(a, "x", lambda _: pytest.fail("pas de vérification"), depot)
    assert r.statut == "arret_generateur"


def test_verificateur_commande_vert_et_rouge(depot: Path):
    assert VerificateurCommande("git status").__call__(depot).ok
    rouge = VerificateurCommande(["git", "show", "branche-absente"])(depot)
    assert not rouge.ok and rouge.code_retour != 0
    absent = VerificateurCommande("programme-introuvable-xyz")(depot)
    assert absent.code_retour == 127
    assert not tous(VerificateurCommande("git status"), VerificateurCommande("programme-introuvable-xyz"))(depot).ok


def test_evaluator_optimizer_tracabilite(depot: Path):
    test = depot / "backend/src/test/java/com/neosoft/neoflow/conges/SoldeTest.java"
    evaluateur = evaluateur_tracabilite(depot, ["EF-06", "EF-07"])
    assert evaluateur(None).score == 0.5  # seul EF-06 a un test étiqueté dans le dépôt
    redacteur = Agent(outils_de_base(depot, Politique.redacteur_tests(depot)), offline=True,
                      approbateur=Approbateur("accord"), client=ModeleSimule([
                          [texte("J'ajoute les tests.")],
                          [outil("editer_fichier", {"chemin": str(test.relative_to(depot)),
                                                    "nouveau": 'class SoldeTest { @Tag("EF-07") void solde() {} }\n'})],
                          [texte("Test EF-07 ajouté.")],
                      ]))
    r = evaluator_optimizer(redacteur, "Prouvez EF-06 et EF-07", evaluateur)
    assert r.statut == "accepte" and [e.score for e in r.evaluations] == [0.5, 1.0]
    assert "EF-07" in redacteur.messages[2]["content"]


def test_orchestrator_workers_paralleles_sur_worktrees_distincts(depot: Path):
    barriere = threading.Barrier(2, timeout=10)  # prouve que les deux workers tournent en même temps

    class ModeleSynchronise(ModeleSimule):
        def creer(self, systeme, messages, outils):
            if self.appels == 0:
                barriere.wait()
            return super().creer(systeme, messages, outils)

    scripts = {
        "conges-back": [[outil("editer_fichier", {"chemin": PROD, "ancien": "return 20;", "nouveau": "return MAX;"})],
                        [outil("editer_fichier", {"chemin": "../neoflow-conges-front/frontend/src/vol.ts", "nouveau": "x"})],
                        [texte("back fait")]],
        "conges-front": [[outil("editer_fichier", {"chemin": "frontend/src/api/conges.ts", "nouveau": "export {}\n"})],
                         [outil("editer_fichier", {"chemin": PROD, "ancien": "return 20;", "nouveau": "return 0;"})],
                         [texte("front fait")]],
    }

    def fabrique(worktree: Path, st: SousTache) -> Agent:
        politique = Politique.generateur(worktree, st.perimetre)
        return Agent(outils_de_base(worktree, politique), offline=True, client=ModeleSynchronise(scripts[st.nom]),
                     approbateur=Approbateur("accord"))

    resultats = orchestrer(depot, [SousTache("conges-back", "voie back", ("backend/*",)),
                                   SousTache("conges-front", "voie front", ("frontend/*",))], fabrique)

    back, front = {r.sous_tache.nom: r for r in resultats}.values()
    assert back.resultat.ok and front.resultat.ok
    assert back.worktree.name == "neoflow-conges-back" and "return MAX;" in (back.worktree / PROD).read_text()
    assert (front.worktree / "frontend/src/api/conges.ts").exists()
    # Isolation : chaque worker est confiné à son worktree et à son périmètre ; le dépôt principal est intact.
    assert not (front.worktree / "frontend/src/vol.ts").exists()
    assert "return 20;" in (front.worktree / PROD).read_text() and "return 20;" in (depot / PROD).read_text()
    assert git(depot, "status", "--porcelain") == ""
    assert {"feat/conges-back", "feat/conges-front"} <= set(git(depot, "branch", "--format=%(refname:short)").split())
    assert "conges-back | termine" in synthese(resultats)


def test_verificateur_perimetre_detecte_un_test_modifie(depot: Path):
    from neoagent.verificateurs import verificateur_perimetre

    git(depot, "switch", "-q", "-c", "feat/conges")
    test = depot / "backend/src/test/java/com/neosoft/neoflow/conges/RegleCongesTest.java"
    assert verificateur_perimetre("main")(depot).ok
    test.write_text(test.read_text().replace("assertEquals(20", "assertEquals(21"))
    verdict = verificateur_perimetre("main")(depot)
    assert not verdict.ok and "existe sur main" in verdict.sortie


def test_sous_agent_a_contexte_isole_et_droits_distincts(depot: Path):
    from neoagent import outil_sous_agent

    test = "backend/src/test/java/com/neosoft/neoflow/conges/PreavisTest.java"
    redacteur = lambda: Agent(outils_de_base(depot, Politique.redacteur_tests(depot)), offline=True,  # noqa: E731
                              approbateur=Approbateur("accord"), client=ModeleSimule([
                                  [outil("editer_fichier", {"chemin": test, "nouveau": '@Tag("EF-10") class PreavisTest {}\n'})],
                                  [outil("editer_fichier", {"chemin": PROD, "ancien": "20", "nouveau": "21"})],
                                  [texte("PreavisTest créé ; le code de production n'est pas dans mes droits.")]]))
    principal = Agent(outils_de_base(depot, Politique.generateur(depot)) + [
        outil_sous_agent("rediger_tests", "Écrit les tests d'une exigence à partir de la spécification. "
                         "À utiliser quand une exigence n'a pas de test. N'écrit jamais de code de production.", redacteur)],
        offline=True, approbateur=Approbateur("accord"), client=ModeleSimule([
            [outil("rediger_tests", {"consigne": "Tests de EF-10 (préavis)"})], [texte("tests délégués")]]))

    r = principal.executer("Implémente EF-10")

    rapport = principal.messages[2]["content"][0]["content"]
    assert r.ok and rapport.startswith("[sous-agent rediger_tests : termine, 3 étapes")
    assert (depot / test).exists() and "return 20;" in (depot / PROD).read_text()  # droits du sous-agent respectés
    assert len(principal.messages) == 4  # le contexte du sous-agent n'a pas rempli celui du principal
