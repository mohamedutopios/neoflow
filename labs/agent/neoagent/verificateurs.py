"""Vérificateurs déterministes : le juge du pattern Generator–Verifier est du code, pas le modèle.

Un vérificateur prend le chemin du worktree et renvoie un `Verdict`. Il s'exécute hors de l'allowlist de
l'agent (c'est le harnais qui le lance) mais sans shell et sans les secrets de l'environnement.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from neoagent.garde_fous import Politique

Verificateur = Callable[[Path], "Verdict"]

# Lignes utiles d'une sortie Maven, Surefire, Failsafe ou Vitest : on les renvoie au modèle, pas tout le log.
LIGNES_UTILES = re.compile(r"(FAIL|ERROR|Tests run:|expected|but was|Expect|AssertionError|Caused by|\bat com\.neosoft|"
                           r"BUILD|✗|×|FAILED|cannot find symbol|error:)", re.IGNORECASE)


@dataclass(frozen=True)
class Verdict:
    ok: bool
    commande: str
    code_retour: int
    sortie: str
    duree_s: float

    def extrait(self, lignes: int = 60) -> str:
        """Ce que l'on renvoie au générateur : les lignes de diagnostic, puis la fin de sortie."""
        utiles = [l for l in self.sortie.splitlines() if LIGNES_UTILES.search(l)]
        corps = utiles[-lignes:] if utiles else self.sortie.splitlines()[-lignes:]
        return "\n".join(corps)


class VerificateurCommande:
    """Lance une commande dans le worktree ; vert si et seulement si le code retour vaut 0."""

    def __init__(self, commande: str | Sequence[str], repertoire: str = ".", timeout_s: int = 1800) -> None:
        self.argv = shlex.split(commande) if isinstance(commande, str) else list(commande)
        self.repertoire = repertoire
        self.timeout_s = timeout_s

    def __repr__(self) -> str:
        return f"VerificateurCommande({' '.join(self.argv)!r}, repertoire={self.repertoire!r})"

    # TODO-J04 verificateur : lancez la commande sans shell ni secrets et renvoyez un Verdict (vert si code retour 0) — TP 2, étape 1
    def __call__(self, worktree: Path) -> Verdict:
        """Lance `self.argv` dans `worktree / self.repertoire`, sans shell, avec `Politique.environnement()` et
        `self.timeout_s` ; vert si et seulement si le code retour vaut 0. Délai dépassé : code 124 ;
        programme introuvable : code 127. Sortie = stdout + stderr ; durée mesurée."""
        raise NotImplementedError("TODO-J04 verificateur : lancez la commande sans shell ni secrets et renvoyez un Verdict (vert si code retour 0) — TP 2, étape 1")


def commande_maven() -> list[str]:
    """`./mvnw` par défaut ; NEOAGENT_MVN permet `mvn -o` sur un poste hors ligne (cache Maven local)."""
    return shlex.split(os.environ.get("NEOAGENT_MVN", "./mvnw"))


def verificateur_maven(cible: str | None = None, *, integration: str | None = None,
                       timeout_s: int = 1800) -> VerificateurCommande:
    """Maven comme vérificateur (backend/).

    - sans argument : `./mvnw -q verify` (tests unitaires + tests d'intégration *IT) ;
    - `cible="RegleCongesTest"` : tests unitaires ciblés (`./mvnw -q test -Dtest=…`) ;
    - `integration="CongesApiIT"` : un test d'intégration ciblé (`verify -Dit.test=… -Dtest=aucun`).
    """
    mvn = commande_maven()
    if integration:
        args = ["-q", "verify", f"-Dit.test={integration}", "-Dtest=aucun", "-Dsurefire.failIfNoSpecifiedTests=false"]
    elif cible:
        args = ["-q", "test", f"-Dtest={cible}", "-Dsurefire.failIfNoSpecifiedTests=false"]
    else:
        args = ["-q", "verify"]
    return VerificateurCommande(mvn + args, repertoire="backend", timeout_s=timeout_s)


def verificateur_vitest(motif: str | None = None, timeout_s: int = 600) -> VerificateurCommande:
    return VerificateurCommande(["npx", "vitest", "run"] + ([motif] if motif else []), repertoire="frontend",
                                timeout_s=timeout_s)


SCRIPT_PERIMETRE = Path(__file__).resolve().parents[1] / "scripts" / "verifier-perimetre.sh"


def verificateur_perimetre(base: str = "main", perimetre: str | None = None, max_lignes: int = 600) -> VerificateurCommande:
    """Contrôle déterministe du diff : fichiers hors périmètre, tests existants modifiés ou désactivés,
    fichiers protégés, dépendances (scripts/verifier-perimetre.sh, également utilisable en CI)."""
    argv = ["bash", str(SCRIPT_PERIMETRE), "--base", base, "--max-lignes", str(max_lignes)]
    if perimetre:
        argv += ["--perimetre", perimetre]
    return VerificateurCommande(argv, timeout_s=120)


def tous(*verificateurs: Verificateur) -> Verificateur:
    """Enchaîne plusieurs vérificateurs ; s'arrête au premier rouge (le moins coûteux d'abord)."""

    def verifier(worktree: Path) -> Verdict:
        derniers: list[Verdict] = []
        for v in verificateurs:
            verdict = v(worktree)
            derniers.append(verdict)
            if not verdict.ok:
                return verdict
        return Verdict(True, " && ".join(v.commande for v in derniers), 0,
                       "\n".join(v.sortie[-2000:] for v in derniers), sum(v.duree_s for v in derniers))

    return verifier
