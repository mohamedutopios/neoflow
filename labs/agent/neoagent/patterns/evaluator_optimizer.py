"""Evaluator–Optimizer : produire, évaluer contre un critère MESURABLE et fixe, critiquer, recommencer
jusqu'au seuil ou à `max_tours`. « Améliore ce code » n'est pas un evaluator-optimizer : il n'y a pas
d'évaluateur.

Évaluateur fourni : `evaluateur_tracabilite`, qui mesure la part des exigences (EF-xx, ENF-xx) prouvées par
au moins un test étiqueté (`@Tag("EF-05")` en JUnit, `[EF-15]` dans un titre Vitest).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from neoagent.agent import Agent, Resultat


@dataclass(frozen=True)
class Evaluation:
    score: float
    accepte: bool
    critique: str


@dataclass
class ResultatEO:
    statut: str  # "accepte", "seuil_non_atteint", "arret_agent"
    evaluations: list[Evaluation] = field(default_factory=list)
    resultats: list[Resultat] = field(default_factory=list)


def evaluator_optimizer(agent: Agent, tache: str, evaluateur: Callable[[Resultat], Evaluation],
                        max_tours: int = 3) -> ResultatEO:
    sortie = ResultatEO("seuil_non_atteint")
    resultat = agent.executer(tache)
    for tour in range(1, max_tours + 1):
        sortie.resultats.append(resultat)
        if not resultat.ok:
            sortie.statut = "arret_agent"
            return sortie
        evaluation = evaluateur(resultat)
        sortie.evaluations.append(evaluation)
        if evaluation.accepte:
            sortie.statut = "accepte"
            return sortie
        if tour < max_tours:
            resultat = agent.poursuivre(f"Évaluation (tour {tour}/{max_tours}) : score {evaluation.score:.2f}, "
                                        f"non accepté.\n{evaluation.critique}\nCorrigez ces points, rien d'autre.")
    return sortie


ETIQUETTE = re.compile(r"""@Tag\(\s*"((?:EF|ENF)-\d{2})"\s*\)|\[((?:EF|ENF)-\d{2})\]""")


def exigences_prouvees(worktree: Path, dossiers: Iterable[str] = ("backend/src/test", "frontend/src")) -> set[str]:
    trouvees: set[str] = set()
    for dossier in dossiers:
        base = Path(worktree) / dossier
        if not base.exists():
            continue
        for fichier in sorted(base.rglob("*")):
            if fichier.suffix in (".java", ".ts", ".tsx") and fichier.is_file():
                for m in ETIQUETTE.finditer(fichier.read_text(encoding="utf-8", errors="ignore")):
                    trouvees.add(m.group(1) or m.group(2))
    return trouvees


def evaluateur_tracabilite(worktree: Path, exigences: Iterable[str], seuil: float = 1.0) -> Callable[[Resultat], Evaluation]:
    attendues = sorted(set(exigences))

    def evaluer(_: Resultat) -> Evaluation:
        prouvees = exigences_prouvees(worktree)
        manquantes = [e for e in attendues if e not in prouvees]
        score = 1.0 if not attendues else (len(attendues) - len(manquantes)) / len(attendues)
        critique = "Toutes les exigences ont un test étiqueté." if not manquantes else (
            "Exigences sans test étiqueté : " + ", ".join(manquantes)
            + ". Ajoutez un test par exigence (@Tag(\"EF-xx\") ou [EF-xx] dans le titre).")
        return Evaluation(score, score >= seuil, critique)

    return evaluer
