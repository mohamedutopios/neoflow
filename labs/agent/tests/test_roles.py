"""Sous-agents par rôle (TP 2) : contexte isolé, droits distincts, description qui fait la délégation."""

from __future__ import annotations

from pathlib import Path

from conftest import outil, texte

from neoagent import Agent, Approbateur, Journal, ModeleSimule, Politique, outils_de_base
from neoagent.roles import outil_redacteur_tests, outil_relecteur

PROD = "backend/src/main/java/com/neosoft/neoflow/conges/RegleConges.java"
NOUVEAU_TEST = "backend/src/test/java/com/neosoft/neoflow/conges/PreavisTest.java"


def scenario(*tours):
    return lambda: ModeleSimule(list(tours))


def test_redacteur_ecrit_des_tests_et_jamais_le_code(depot: Path):
    journal = Journal()
    redacteur = outil_redacteur_tests(depot, approbateur=Approbateur("accord"), journal=journal, offline=True,
                                      fabrique_client=scenario(
        [outil("editer_fichier", {"chemin": NOUVEAU_TEST, "nouveau": '@Tag("EF-10") class PreavisTest {}\n'})],
        [outil("editer_fichier", {"chemin": PROD, "ancien": "return 20;", "nouveau": "return 25;"})],
        [texte("Test créé : PreavisTest [EF-10]. Le code de production n'est pas de mon ressort.")]))

    assert redacteur.name == "rediger_tests" and redacteur.risque == "ecriture"
    assert "Ne l'utilisez pas" in redacteur.description  # la description dit aussi quand NE PAS déléguer
    rapport = redacteur.handler({"consigne": "EF-10 : un test par exemple de conges_preavis.feature"})

    assert rapport.startswith("[sous-agent rediger_tests : termine, 3 étapes")
    assert (depot / NOUVEAU_TEST).exists()
    assert "return 20;" in (depot / PROD).read_text()  # écriture du code refusée par Politique.redacteur_tests
    assert any(e["type"] == "erreur" and "périmètre" in (e["sortie_extrait"] or "") for e in journal.evenements)


def test_relecteur_en_lecture_seule_sans_approbation(depot: Path):
    relecteur = outil_relecteur(depot, offline=True, fabrique_client=scenario(
        [outil("git_diff", {})],
        [outil("editer_fichier", {"chemin": PROD, "ancien": "return 20;", "nouveau": "return 21;"})],
        [texte("EF-06 | couverte | RegleConges.java:4 | RegleCongesTest.dureeMax")]))

    assert relecteur.name == "relire_diff" and relecteur.risque == "lecture"
    rapport = relecteur.handler({"consigne": "Relisez EF-06 contre docs/specs/CONGES.md"})
    assert "EF-06 | couverte" in rapport
    assert "return 20;" in (depot / PROD).read_text()


def test_agent_principal_ne_voit_que_le_rapport(depot: Path):
    redacteur = outil_redacteur_tests(depot, approbateur=Approbateur("accord"), offline=True,
                                      fabrique_client=scenario(
        [outil("lire_fichier", {"chemin": "docs/specs/CONGES.md"})],
        [outil("editer_fichier", {"chemin": NOUVEAU_TEST, "nouveau": "class PreavisTest {}\n"})],
        [texte("Créé : " + NOUVEAU_TEST)]))
    politique = Politique.generateur(depot)
    principal = Agent(outils_de_base(depot, politique) + [redacteur], offline=True,
                      approbateur=Approbateur("accord"), client=ModeleSimule([
        [outil("rediger_tests", {"consigne": "EF-10 : tests du préavis, avant le code"})],
        [texte("Tests reçus, j'implémente ensuite.")]]))

    r = principal.executer("T07, EF-10")

    assert r.ok and r.appels_outils == ["rediger_tests"]
    resultat = principal.messages[2]["content"][0]["content"]
    assert resultat.startswith("[sous-agent rediger_tests : termine") and NOUVEAU_TEST in resultat
    # Contexte isolé : la spécification lue par le sous-agent n'entre pas dans l'historique du principal.
    assert "Spécification CONGES" not in str(principal.messages)
