"""Orchestrator-workers : l'orchestrateur découpe, chaque worker travaille dans SON worktree, avec SON agent
(contexte isolé, politique limitée à son worktree et à son périmètre), en parallèle. L'humain fusionne.

Les worktrees sont créés séquentiellement (verrous Git), puis les workers tournent dans un pool de threads.
Utile quand les sous-tâches sont indépendantes (voie back, voie front) ; inutile pour une tâche de 3 fichiers.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from neoagent.agent import Agent, Resultat
from neoagent.verificateurs import Verdict, Verificateur
from neoagent.worktrees import creer_worktree, diff_stat


@dataclass(frozen=True)
class SousTache:
    nom: str                          # nom du worktree et de la branche feat/<nom>
    consigne: str
    perimetre: tuple[str, ...] = ("*",)


@dataclass
class ResultatWorker:
    sous_tache: SousTache
    worktree: Path
    resultat: Resultat
    diff: str
    verdict: Verdict | None = None


DECOUPAGE_NEOFLOW = (
    SousTache("conges-back", "Voie back de la variante CONGES : tâches T02 à T09 de docs/specs/conges/PLAN_TACHES.md.",
              ("backend/*",)),
    SousTache("conges-front", "Voie front de la variante CONGES : tâches T01 et T10, contre le contrat OpenAPI.",
              ("frontend/*",)),
)


# TODO-J04 orchestrateur : créez les worktrees en séquence, puis un agent neuf par worker dans un pool de threads — TP 3
def orchestrer(repo: Path, sous_taches: list[SousTache] | tuple[SousTache, ...],
               fabrique_agent: Callable[[Path, SousTache], Agent], *, base: str = "HEAD", max_workers: int = 2,
               verificateur: Verificateur | None = None) -> list[ResultatWorker]:
    """Un worktree et un agent neuf par sous-tâche, en parallèle ; vérificateur du worker s'il a terminé.

    1. noms distincts (ValueError sinon) ; 2. worktrees créés EN SÉQUENCE avec `creer_worktree` (verrous Git) ;
    3. `ThreadPoolExecutor(max_workers)` : chaque worker appelle `fabrique_agent(worktree, sous_tache)`,
       exécute sa consigne, lance `verificateur(worktree)` si le résultat est « termine », puis `diff_stat` ;
    4. résultats dans l'ordre des sous-tâches. L'humain fusionne : rien n'est commité ni fusionné ici.
    """
    raise NotImplementedError("TODO-J04 orchestrateur : créez les worktrees en séquence, puis un agent neuf par worker dans un pool de threads — TP 3")


def synthese(resultats: list[ResultatWorker]) -> str:
    """Rapport de l'orchestrateur pour l'humain : il décide de la fusion."""
    lignes = ["| Worker | Statut | Étapes | Tokens | Vérificateur | Diff |", "|---|---|---|---|---|---|"]
    for r in resultats:
        verdict = "—" if r.verdict is None else ("vert" if r.verdict.ok else "rouge")
        diff = (r.diff.splitlines() or ["(aucun)"])[-1]
        lignes.append(f"| {r.sous_tache.nom} | {r.resultat.statut} | {r.resultat.etapes} | {r.resultat.tokens} | "
                      f"{verdict} | {diff} |")
    return "\n".join(lignes)
