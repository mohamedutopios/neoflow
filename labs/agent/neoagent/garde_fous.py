"""Garde-fous déterministes de neoagent (J2 transposé dans le code).

Le modèle ne décide jamais seul de ce qui est permis : chaque outil passe par la `Politique`.
- chemins limités au worktree (`racine`), chemins interdits même en lecture ;
- lecture seule par défaut ;
- écriture limitée à des motifs, tests et spécifications protégés pour le générateur ;
- commandes : allowlist par préfixe de jetons, sans shell, sans opérateurs, sans secrets dans l'environnement.

Une règle enfreinte lève `RefusGardeFou` : l'agent renvoie le message au modèle comme résultat d'outil
en erreur (`is_error`), et le journal le trace.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shlex
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath


class RefusGardeFou(Exception):
    """Action refusée par la politique (chemin, écriture, commande)."""


# Commandes de lecture : seules autorisées en lecture seule.
COMMANDES_LECTURE: tuple[str, ...] = (
    "git status",
    "git diff",
    "git log",
    "git show",
)

# Allowlist complète (mode écriture) : tests, build, lint du socle NeoFlow.
COMMANDES_PAR_DEFAUT: tuple[str, ...] = COMMANDES_LECTURE + (
    "./mvnw -q test",
    "./mvnw test",
    "./mvnw -q verify",
    "./mvnw verify",
    "./mvnw -q compile",
    "npm test",
    "npm run test",
    "npm run lint",
    "npm run typecheck",
    "npx vitest run",
    "npx tsc --noEmit",
)

# Interdits même en lecture : secrets, métadonnées Git, artefacts.
CHEMINS_INTERDITS_PAR_DEFAUT: tuple[str, ...] = (
    ".git",
    ".git/*",
    "*/.git/*",
    ".env",
    "*.env",
    ".env.*",
    "*/.env",
    "*/.env.*",
    "*secrets*",
    "*.pem",
    "*.key",
    "*id_rsa*",
)

# Protégés en écriture pour l'agent générateur : les preuves, la spécification, le legacy, les dépendances.
PROTEGES_GENERATEUR: tuple[str, ...] = (
    "*/src/test/*",
    "src/test/*",
    "*.test.ts",
    "*.test.tsx",
    "*.spec.ts",
    "e2e/*",
    "docs/specs/*",
    "docs/adr/*",
    "backend/src/main/java/com/neosoft/neoflow/legacy/*",
    "frontend/src/legacy/*",
    "*/pom.xml",
    "pom.xml",
    "*/package.json",
    "*/package-lock.json",
    ".github/*",
    "labs/*",
)

# Opérateurs de shell : jamais acceptés, la commande est exécutée sans shell.
OPERATEURS_INTERDITS = re.compile(r"[;&|<>`$\\\n\r]|\(|\)")

# Arguments qui transforment une commande de lecture en écriture ou en exécution arbitraire.
ARGUMENTS_INTERDITS: tuple[str, ...] = ("--output", "--exec", "--upload-pack", "--receive-pack", "--ext-diff")

# Variables d'environnement jamais transmises aux commandes lancées par l'agent.
SECRETS_ENV = re.compile(r"(API_KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|^AWS_|^ANTHROPIC_)", re.IGNORECASE)


@dataclass(frozen=True)
class Politique:
    """Ce que les outils ont le droit de faire, pour un worktree donné."""

    racine: Path
    lecture_seule: bool = True
    commandes_autorisees: tuple[str, ...] = COMMANDES_PAR_DEFAUT
    chemins_interdits: tuple[str, ...] = CHEMINS_INTERDITS_PAR_DEFAUT
    chemins_ecriture: tuple[str, ...] = ("*",)
    chemins_proteges: tuple[str, ...] = ()
    timeout_commande_s: int = 900
    taille_max_lecture: int = 60_000
    taille_max_sortie: int = 12_000
    ignores_parcours: tuple[str, ...] = field(default=(".git", "node_modules", "target", "dist", ".venv", "__pycache__"))

    # ------------------------------------------------------------------ préréglages

    @classmethod
    def lecture(cls, racine: Path) -> Politique:
        """Exploration et revue : aucune écriture, commandes Git de lecture seulement."""
        return cls(racine=Path(racine))

    @classmethod
    def generateur(cls, racine: Path, chemins_ecriture: tuple[str, ...] = ("*",)) -> Politique:
        """Implémentation : écrit le code de production, jamais les tests, la spec, le legacy, les dépendances."""
        return cls(racine=Path(racine), lecture_seule=False, chemins_ecriture=chemins_ecriture,
                   chemins_proteges=PROTEGES_GENERATEUR)

    @classmethod
    def redacteur_tests(cls, racine: Path) -> Politique:
        """Écriture des preuves : seulement les dossiers et fichiers de test."""
        return cls(racine=Path(racine), lecture_seule=False,
                   chemins_ecriture=("*/src/test/*", "src/test/*", "*.test.ts", "*.test.tsx"))

    def avec(self, **modifications) -> Politique:
        return replace(self, **modifications)

    # ------------------------------------------------------------------ chemins

    def relatif(self, chemin: Path) -> str:
        return PurePosixPath(chemin.resolve().relative_to(self.racine.resolve())).as_posix()

    # TODO-J04 garde-fous-chemins : résolvez le chemin dans le worktree (refus hors racine et chemins interdits), puis contrôlez l'écriture (lecture seule, périmètre, fichiers protégés) — TP 1, étape 2
    def resoudre(self, chemin: str) -> Path:
        """Chemin absolu dans le worktree ; refuse toute sortie de `racine` et les chemins interdits.

        `..`, chemins absolus et liens symboliques sont résolus avant la vérification : un lien qui pointe
        hors du worktree est refusé comme un chemin explicite.
        """
        raise NotImplementedError("TODO-J04 garde-fous-chemins : résolvez le chemin dans le worktree (refus hors racine et chemins interdits), puis contrôlez l'écriture (lecture seule, périmètre, fichiers protégés) — TP 1, étape 2")

    def verifier_ecriture(self, chemin: str) -> Path:
        """Chemin autorisé en écriture : pas en lecture seule, dans `chemins_ecriture`, hors `chemins_proteges`."""
        raise NotImplementedError("TODO-J04 garde-fous-chemins : résolvez le chemin dans le worktree (refus hors racine et chemins interdits), puis contrôlez l'écriture (lecture seule, périmètre, fichiers protégés) — TP 1, étape 2")

    @staticmethod
    def _correspond(relatif: str, motifs: tuple[str, ...]) -> bool:
        # fnmatch : « * » couvre aussi les « / », comme dans les permissions OpenCode du J2.
        return any(fnmatch.fnmatchcase(relatif, m) or fnmatch.fnmatchcase("/" + relatif, "*/" + m) for m in motifs)

    # ------------------------------------------------------------------ commandes

    # TODO-J04 garde-fous-commandes : découpez la commande sans shell, refusez opérateurs, arguments dangereux et commandes hors allowlist (lecture seule : Git en lecture) — TP 1, étape 3
    def verifier_commande(self, commande: str, repertoire: str | None = None) -> tuple[list[str], Path]:
        """Découpe et contrôle une commande ; renvoie (argv, répertoire d'exécution).

        Refusée si : opérateur de shell, argument dangereux, hors allowlist (préfixe de jetons), ou commande
        d'écriture ou d'exécution alors que la politique est en lecture seule.
        """
        raise NotImplementedError("TODO-J04 garde-fous-commandes : découpez la commande sans shell, refusez opérateurs, arguments dangereux et commandes hors allowlist (lecture seule : Git en lecture) — TP 1, étape 3")

    @staticmethod
    def environnement() -> dict[str, str]:
        """Environnement des commandes lancées par l'agent, sans clé ni jeton."""
        return {k: v for k, v in os.environ.items() if not SECRETS_ENV.search(k)}
