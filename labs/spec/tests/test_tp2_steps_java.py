"""TP 2 — génération des squelettes de step definitions Cucumber-JVM."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from neospec.steps_java import (Etape, TypePerso, charger_types, collecter_etapes, expression_cucumber,
                                generer_classe, unifier)

LAB = Path(__file__).resolve().parents[1]
TYPES = [TypePerso("sousType", ("CP", "RTT", "SANS_SOLDE")), TypePerso("debut", ("au matin", "l'après-midi"))]


@pytest.mark.parametrize("texte, attendu", [
    ('"alice" a déjà 20 jours en 2027', ('{string} a déjà {int} jours en {int}', ["string", "int", "int"])),
    ("le nombre de jours ouvrés décomptés est 1,5", ("le nombre de jours ouvrés décomptés est {decimal}", ["decimal"])),
    ('"alice" crée une demande de congés CP du "2026-12-21" au "2026-12-24"',
     ("{string} crée une demande de congés {sousType} du {string} au {string}", ["string", "sousType", "string", "string"])),
    ('commençant le "2026-12-17" l\'après-midi', ("commençant le {string} {debut}", ["string", "debut"])),
    ("la simulation (HTTP 400) et/ou {x}", ("la simulation \\(HTTP {int}\\) et\\/ou \\{x\\}", ["int"])),
    ("aucun champ montant n'est proposé", ("aucun champ montant n'est proposé", [])),
])
def test_expression_cucumber(texte, attendu):
    assert expression_cucumber(texte, TYPES) == attendu


def test_mots_entiers_seulement():
    assert expression_cucumber("la CPAM et le RTTx", TYPES) == ("la CPAM et le RTTx", [])


def test_unifier_entiers_et_decimaux():
    etapes = [Etape("Alors", "le nombre de jours ouvrés décomptés est 4", None, {"EF-04"}, "a.feature:3"),
              Etape("Alors", "le nombre de jours ouvrés décomptés est 1,5", None, {"EF-03"}, "a.feature:9"),
              Etape("Soit", "le nombre de jours ouvrés décomptés est 20", None, {"EF-06"}, "b.feature:4")]
    defs = unifier(etapes, [])
    assert len(defs) == 1
    assert defs[0].expression == "le nombre de jours ouvrés décomptés est {decimal}"
    assert defs[0].exigences == {"EF-03", "EF-04", "EF-06"} and defs[0].mot_cle == "Alors"


def test_classe_generee(fixture_generation, tmp_path):
    for f in fixture_generation["features"]:
        (tmp_path / f["fichier"]).write_text(f["contenu"], encoding="utf-8")
    types = charger_types(LAB / "exemples" / "parametres_CONGES.yaml")
    defs = unifier(collecter_etapes(sorted(tmp_path.glob("*.feature"))), types)
    expressions = [d.expression for d in defs]
    assert len(expressions) == len(set(expressions))
    source = generer_classe(defs, "com.neosoft.neoflow.acceptance.conges", "CongesSteps", types, "features")
    assert "@ParameterType(\"SANS_SOLDE|RTT|CP\")" in source
    assert "@Quand(\"{string} crée une demande de congés {sousType} du {string} au {string}\")" in source
    assert "DataTable table" in source and source.count("throw new PendingException") == len(defs)


def _jar(nom: str) -> Path | None:
    jars = sorted((Path.home() / ".m2" / "repository").glob(f"io/cucumber/{nom}/7.*/{nom}-7.*.jar"))
    return jars[-1] if jars else None


@pytest.mark.skipif(shutil.which("javac") is None or _jar("cucumber-java") is None,
                    reason="javac ou cucumber-java absent du dépôt Maven local")
def test_compilation_javac(fixture_generation, tmp_path):
    for f in fixture_generation["features"]:
        (tmp_path / f["fichier"]).write_text(f["contenu"], encoding="utf-8")
    types = charger_types(LAB / "exemples" / "parametres_CONGES.yaml")
    defs = unifier(collecter_etapes(sorted(tmp_path.glob("*.feature"))), types)
    src = tmp_path / "src" / "CongesSteps.java"
    src.parent.mkdir()
    src.write_text(generer_classe(defs, "com.neosoft.neoflow.acceptance.conges", "CongesSteps", types, "features"), encoding="utf-8")
    version = _jar("cucumber-java").parent.name
    cp = [_jar("cucumber-java")] + sorted((Path.home() / ".m2" / "repository").glob(f"io/cucumber/datatable/{version}/*.jar"))
    r = subprocess.run(["javac", "-encoding", "UTF-8", "-d", str(tmp_path / "out"), "-cp", ":".join(map(str, cp)), str(src)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
