"""Fixtures : dépôt Git jetable façon NeoFlow + dossier d'état isolé. Aucun réseau, aucune clé."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
os.environ["NEOFLOW_RAG"] = "off"  # tests déterministes : pas de lab RAG ni de Qdrant

FICHIERS = {
    "backend/src/main/java/com/neosoft/neoflow/validation/CircuitValidationService.java": """\
package com.neosoft.neoflow.validation;

import com.neosoft.neoflow.demande.Demande;
import com.neosoft.neoflow.legacy.RegleValidationLegacy;
import org.springframework.stereotype.Service;

@Service
public class CircuitValidationService {

    /** Calcule le niveau de validation (1..3) d'une demande au moment de la soumission. */
    public int calculerNiveau(Demande d, int ancienneteMois) {
        Double montant = d.getMontant() != null ? d.getMontant().doubleValue() : 0.0;
        return RegleValidationLegacy.determinerNiveau(d.getType().name(), montant, ancienneteMois,
                d.getDepartement(), d.isUrgent());
    }
}
""",
    "backend/src/main/java/com/neosoft/neoflow/legacy/RegleValidationLegacy.java": """\
package com.neosoft.neoflow.legacy;

public class RegleValidationLegacy {

    public static int NIVEAU_MAX = 3;

    private static final String DSI = "DSI";

    /** Retourne le niveau de validation (1, 2 ou 3). */
    public static int determinerNiveau(String type, Double montant, int ancienneteMois, String departement, boolean urgent) {
        int niveau = 1;
        double m = montant.doubleValue();
        if (type.equals("ACHAT")) {
            if (m >= 1000) {
                niveau = 2;
            }
            if (m > 5000) {
                niveau = 3;
            }
        } else if (type.equals("MATERIEL_IT")) {
            if (departement == DSI) {
                niveau = 1;
            }
        }
        return Math.min(niveau, NIVEAU_MAX);
    }
}
""",
    "docs/adr/ADR-001-circuit-validation.md": """\
# ADR-001 — Circuit de validation

## Décision
Le niveau de validation est calculé à la soumission par CircuitValidationService, qui délègue
au module legacy RegleValidationLegacy. Le montant nul est converti en 0.0 par l'adaptateur.

## Conséquences
Toute modification des seuils passe par des tests de caractérisation (J8).
""",
    "frontend/src/legacy/utils-legacy.js": """\
function formatMontant(m) {
  return m.toFixed(2) + ' EUR';
}
""",
    "frontend/node_modules/lib/index.js": "module.exports = 42;\n",
}


def _git(depot: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "Formateur", "GIT_AUTHOR_EMAIL": "formateur@example.com",
           "GIT_COMMITTER_NAME": "Formateur", "GIT_COMMITTER_EMAIL": "formateur@example.com",
           "GIT_AUTHOR_DATE": "2026-11-02T09:00:00+01:00", "GIT_COMMITTER_DATE": "2026-11-02T09:00:00+01:00"}
    return subprocess.run(["git", "-C", str(depot), *args], check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


class Depot:
    def __init__(self, racine: Path):
        self.racine = racine

    def git(self, *args: str) -> str:
        return _git(self.racine, *args)

    def ecrire(self, chemin: str, contenu: str) -> None:
        f = self.racine / chemin
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(contenu, encoding="utf-8")

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def lire(self, chemin: str) -> str:
        return (self.racine / chemin).read_text(encoding="utf-8")


@pytest.fixture
def depot(tmp_path: Path) -> Depot:
    d = Depot(tmp_path / "neoflow")
    d.racine.mkdir()
    d.git("init", "-q", "-b", "main")
    for chemin, contenu in FICHIERS.items():
        d.ecrire(chemin, contenu)
    d.commit("feat: socle NeoFlow (circuit de validation)")
    return d


@pytest.fixture
def etat(tmp_path: Path) -> Path:
    e = tmp_path / "etat"
    e.mkdir()
    return e
