from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from neoagent.garde_fous import Politique, RefusGardeFou
from neoagent.tools import ErreurOutil, Tool, outils_de_base

PROD = "backend/src/main/java/com/neosoft/neoflow/conges/RegleConges.java"


def outils(politique: Politique) -> dict[str, Tool]:
    return {o.name: o for o in outils_de_base(politique.racine, politique)}


def test_contrat_tool_et_six_outils_de_base(depot: Path):
    o = outils(Politique.lecture(depot))
    assert list(o) == ["lire_fichier", "chercher", "lister", "editer_fichier", "executer_commande", "git_diff"]
    assert {n: t.risque for n, t in o.items()} == {"lire_fichier": "lecture", "chercher": "lecture", "lister": "lecture",
                                                   "editer_fichier": "ecriture", "executer_commande": "execution",
                                                   "git_diff": "lecture"}
    assert o["lire_fichier"].definition()["input_schema"]["required"] == ["chemin"]


@pytest.mark.parametrize("nom", ["Lire", "lire-fichier", "", "x" * 65])
def test_nom_d_outil_valide(nom: str):
    with pytest.raises(ValueError):
        Tool(nom, "d", {"type": "object", "properties": {}}, lambda e: "")


def test_lire_fichier_numerote_et_borne(depot: Path):
    sortie = outils(Politique.lecture(depot))["lire_fichier"].handler({"chemin": PROD, "debut": 3, "fin": 4})
    assert sortie.splitlines() == ["    3\tpublic class RegleConges {", "    4\t    int dureeMax() { return 20; }"]


def test_lire_fichier_interdit(depot: Path):
    with pytest.raises(RefusGardeFou):
        outils(Politique.lecture(depot))["lire_fichier"].handler({"chemin": ".env"})


def test_chercher_est_deterministe_et_ignore_les_secrets(depot: Path):
    sortie = outils(Politique.lecture(depot))["chercher"].handler({"motif": "dureeMax|ANTHROPIC"})
    assert sortie.splitlines() == [
        "backend/src/main/java/com/neosoft/neoflow/conges/RegleConges.java:4: int dureeMax() { return 20; }",
        'backend/src/test/java/com/neosoft/neoflow/conges/RegleCongesTest.java:2: @Tag("EF-06") void dureeMax() '
        '{ assertEquals(20, regle.dureeMax()); }',
    ]


def test_lister_ignore_git_et_secrets(depot: Path):
    sortie = outils(Politique.lecture(depot))["lister"].handler({"profondeur": 9})
    assert ".env" not in sortie.splitlines() and not any(l.startswith(".git/") for l in sortie.splitlines())
    assert PROD in sortie


def test_editer_fichier_remplace_un_extrait_unique(depot: Path):
    o = outils(Politique.generateur(depot))
    entree = {"chemin": PROD, "ancien": "return 20;", "nouveau": "return DUREE_MAX;"}
    assert "+    int dureeMax() { return DUREE_MAX; }" in o["editer_fichier"].apercu(entree)
    o["editer_fichier"].handler(entree)
    assert "return DUREE_MAX;" in (depot / PROD).read_text()


def test_editer_fichier_cree_un_fichier(depot: Path):
    outils(Politique.generateur(depot))["editer_fichier"].handler(
        {"chemin": "backend/src/main/java/com/neosoft/neoflow/conges/Jours.java", "nouveau": "class Jours {}\n"})
    assert (depot / "backend/src/main/java/com/neosoft/neoflow/conges/Jours.java").exists()


def test_editer_fichier_extrait_absent_ou_ambigu(depot: Path):
    o = outils(Politique.generateur(depot))
    with pytest.raises(ErreurOutil, match="introuvable"):
        o["editer_fichier"].handler({"chemin": PROD, "ancien": "n'existe pas", "nouveau": "x"})
    with pytest.raises(ErreurOutil, match="ambigu"):
        o["editer_fichier"].handler({"chemin": PROD, "ancien": "}", "nouveau": "x"})


def test_editer_fichier_refuse_en_lecture_seule_et_sur_un_test(depot: Path):
    with pytest.raises(RefusGardeFou, match="lecture seule"):
        outils(Politique.lecture(depot))["editer_fichier"].handler({"chemin": PROD, "ancien": "20", "nouveau": "21"})
    with pytest.raises(RefusGardeFou, match="protégé"):
        outils(Politique.generateur(depot))["editer_fichier"].handler(
            {"chemin": "backend/src/test/java/com/neosoft/neoflow/conges/RegleCongesTest.java",
             "ancien": "assertEquals(20", "nouveau": "assertEquals(21"})


def test_executer_commande_allowlistee(depot: Path):
    sortie = outils(Politique.lecture(depot))["executer_commande"].handler({"commande": "git log --oneline -1"})
    assert sortie.startswith("code retour 0") and "socle" in sortie


def test_executer_commande_hors_allowlist(depot: Path):
    with pytest.raises(RefusGardeFou):
        outils(Politique.generateur(depot))["executer_commande"].handler({"commande": "rm -rf backend"})
    assert (depot / "backend").exists()


def test_executer_commande_delai(depot: Path, monkeypatch):
    def lent(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", lent)
    with pytest.raises(ErreurOutil, match="délai dépassé"):
        outils(Politique.lecture(depot).avec(timeout_commande_s=1))["executer_commande"].handler({"commande": "git status"})


def test_git_diff_montre_modifications_et_fichiers_nouveaux(depot: Path):
    (depot / PROD).write_text("modifié\n")
    (depot / "frontend/src/api.ts").write_text("export {}\n")
    sortie = outils(Politique.lecture(depot))["git_diff"].handler({"stat": True})
    assert "RegleConges.java" in sortie and "frontend/src/api.ts" in sortie
