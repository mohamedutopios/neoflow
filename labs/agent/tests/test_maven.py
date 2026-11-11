"""Generator–Verifier réel sur une copie du socle NeoFlow : Maven est le vérificateur.

Lent (une à deux minutes) : lancé seulement si NEOAGENT_TESTS_MAVEN=1 et NEOFLOW_RACINE pointe vers le dépôt
NeoFlow (dans le socle : la racine est deux niveaux au-dessus de labs/agent). Sur un poste sans accès au
dépôt Maven distant, NEOAGENT_MVN="mvn -o" utilise le cache local.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from conftest import git

from neoagent import Agent, Approbateur, Journal, ModeleSimule, Politique, outils_de_base
from neoagent.patterns import generator_verifier
from neoagent.verificateurs import verificateur_maven

SCENARIO = Path(__file__).resolve().parents[1] / "scenarios" / "gv_registre.json"
REGISTRE = "backend/src/main/java/com/neosoft/neoflow/regles/RegleMetierRegistry.java"
CORRECT = ".filter(regle -> regle.type() == TypeDemande.GENERIQUE || regle.type() == type)"
BOGUE = ".filter(regle -> regle.type() == type)"


def _racine() -> Path | None:
    candidat = Path(os.environ.get("NEOFLOW_RACINE", Path(__file__).resolve().parents[3]))
    return candidat if (candidat / "backend" / "pom.xml").exists() else None


pytestmark = [
    pytest.mark.maven,
    pytest.mark.skipif(os.environ.get("NEOAGENT_TESTS_MAVEN") != "1", reason="NEOAGENT_TESTS_MAVEN=1 requis"),
    pytest.mark.skipif(_racine() is None, reason="socle NeoFlow introuvable (NEOFLOW_RACINE)"),
]


def test_generator_verifier_corrige_un_test_rouge_sur_le_socle(tmp_path: Path):
    copie = tmp_path / "neoflow"
    shutil.copytree(_racine() / "backend", copie / "backend", ignore=shutil.ignore_patterns("target"))
    git(tmp_path, "init", "-q", "-b", "main", str(copie))
    for cle, valeur in (("user.email", "t@neoflow.example"), ("user.name", "t")):
        git(copie, "config", cle, valeur)
    git(copie, "add", "-A")
    git(copie, "commit", "-q", "-m", "socle")
    source = (copie / REGISTRE).read_text(encoding="utf-8")
    assert CORRECT in source
    (copie / REGISTRE).write_text(source.replace(CORRECT, BOGUE), encoding="utf-8")
    git(copie, "commit", "-qam", "bogue injecté : les règles GENERIQUE ne s'appliquent plus")

    verificateur = verificateur_maven(cible="RegleMetierRegistryTest")
    assert not verificateur(copie).ok  # rouge avant l'agent
    journal = Journal(tmp_path / "traj.jsonl")
    generateur = Agent(outils_de_base(copie, Politique.generateur(copie)), offline=True, journal=journal,
                       approbateur=Approbateur("accord"), client=ModeleSimule.depuis_fichier(SCENARIO))

    r = generator_verifier(generateur, "Les tests du registre de règles sont rouges : corrigez.", verificateur, copie)

    assert r.ok and r.tours == 2 and [v.ok for v in r.verdicts] == [False, True]
    assert "appliqueLesReglesGeneriquesATousLesTypes" in generateur.messages[4]["content"]
    assert git(copie, "diff", "--name-only").split() == [REGISTRE]
    assert CORRECT in (copie / REGISTRE).read_text(encoding="utf-8")
    assert json.loads((tmp_path / "traj.jsonl").read_text().splitlines()[-1])["type"] == "fin"
