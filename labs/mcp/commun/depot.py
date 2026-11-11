"""Accès au dépôt NeoFlow : racine, validation des chemins, métadonnées Git.

Toutes les lectures de fichiers des serveurs passent par `resoudre_chemin()` :
chemin relatif obligatoire, pas de sortie du dépôt (y compris par lien symbolique),
fichiers sensibles refusés même s'ils sont versionnés.
"""
from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import time
from functools import lru_cache
from pathlib import Path, PurePosixPath

LAB_DIR = Path(__file__).resolve().parent.parent          # labs/mcp
RACINE_PAR_DEFAUT = LAB_DIR.parent.parent                   # racine du dépôt NeoFlow

# Motifs refusés (chemin relatif POSIX ou nom de fichier). Complétables par NEOFLOW_MCP_DENY.
MOTIFS_INTERDITS = [
    ".env", ".env.*", "**/.env", "**/.env.*",
    "**/secrets/**", "secrets/**",
    "*.pem", "*.key", "*.p12", "*.jks", "id_rsa*", "id_ed25519*",
    ".git/**", "**/.git/**",
    "**/application-prod*.yml", "**/*-prod.yml",
]
MOTIFS_AUTORISES = [".env.example", "**/.env.example"]

SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


class CheminRefuse(ValueError):
    """Chemin hors périmètre ou sensible : à transformer en refus MCP par l'appelant."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def racine_depot() -> Path:
    return Path(os.environ.get("NEOFLOW_REPO") or RACINE_PAR_DEFAUT).resolve()


def motifs_interdits() -> list[str]:
    extra = [m.strip() for m in os.environ.get("NEOFLOW_MCP_DENY", "").split(",") if m.strip()]
    return MOTIFS_INTERDITS + extra


def _correspond(rel: str, motifs: list[str]) -> bool:
    nom = PurePosixPath(rel).name
    return any(fnmatch.fnmatchcase(rel, m) or fnmatch.fnmatchcase(nom, m) for m in motifs)


def est_interdit(rel: str) -> bool:
    rel = PurePosixPath(rel.replace("\\", "/")).as_posix()   # « ./a/b » -> « a/b »
    if _correspond(rel, MOTIFS_AUTORISES):
        return False
    return _correspond(rel, motifs_interdits())


def resoudre_chemin(rel: str, racine: Path | None = None) -> tuple[Path, str]:
    """Valide un chemin fourni par le modèle et renvoie (chemin absolu, chemin relatif POSIX).

    TODO T2.2 (TP 2) — Lever CheminRefuse(code, message), dans cet ordre :
      - chemin vide ou contenant un octet nul           -> "chemin_invalide"
      - chemin absolu ("/..." ou "C:...")                -> "chemin_absolu"
      - un segment ".."                                  -> "traversee"
      - chemin RÉSOLU (liens suivis) hors de la racine   -> "hors_depot"   (Path.resolve + is_relative_to)
      - fichier sensible (est_interdit)                  -> "fichier_sensible"
    En l'état, N'IMPORTE QUEL chemin est accepté (y compris /etc/passwd ou .env).
    """
    racine = racine or racine_depot()
    cible = (racine / rel).resolve()
    relatif = cible.relative_to(racine).as_posix() if cible.is_relative_to(racine) else rel
    return cible, relatif


# --------------------------------------------------------------------------- #
# Git
# --------------------------------------------------------------------------- #

def git(racine: Path, *args: str, timeout: int = 10) -> str | None:
    """Exécute git sans shell ; renvoie stdout ou None (pas un dépôt, commande en échec)."""
    try:
        res = subprocess.run(["git", "-C", str(racine), *args], capture_output=True,
                             text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout if res.returncode == 0 else None


@lru_cache(maxsize=8)
def _head_cache(racine: str, _jeton: int) -> str:
    out = git(Path(racine), "rev-parse", "--short=7", "HEAD")
    return out.strip() if out else "nogit"


def head_commit(racine: Path | None = None) -> str:
    racine = racine or racine_depot()
    # Cache de 5 s : évite un appel git par résultat sans servir un HEAD périmé.
    return _head_cache(str(racine), int(time.time() // 5))


def fichiers_modifies(racine: Path | None = None) -> set[str]:
    """Fichiers modifiés dans l'arbre de travail (non commités)."""
    racine = racine or racine_depot()
    out = git(racine, "status", "--porcelain", "--untracked-files=no") or ""
    return {ligne[3:].strip() for ligne in out.splitlines() if len(ligne) > 3}


def fichier_change_depuis(commit: str, rel: str, racine: Path | None = None) -> bool | None:
    """True si `rel` a changé entre `commit` et HEAD ; None si le commit est inconnu."""
    racine = racine or racine_depot()
    commit = commit.split("+", 1)[0]
    if not SHA_RE.match(commit):
        return None
    try:
        res = subprocess.run(["git", "-C", str(racine), "diff", "--quiet", commit, "HEAD", "--", rel],
                             capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode in (0, 1):
        return res.returncode == 1
    return None


def lire_a_la_revision(commit: str, rel: str, racine: Path | None = None) -> str | None:
    """Contenu de `rel` au commit donné (git show commit:chemin), chemin déjà validé."""
    racine = racine or racine_depot()
    if not SHA_RE.match(commit):
        return None
    return git(racine, "show", f"{commit}:{rel}")


def fichiers_versionnes(racine: Path | None = None) -> list[str]:
    """Fichiers suivis par Git (respecte .gitignore) ; repli : parcours du dossier."""
    racine = racine or racine_depot()
    out = git(racine, "ls-files", "-z", timeout=20)
    if out is not None:
        return [f for f in out.split("\x00") if f]
    fichiers = []
    for dossier, sous, noms in os.walk(racine):
        sous[:] = [s for s in sous if s not in {".git", "node_modules", "target", "dist", ".venv", "var"}]
        for nom in noms:
            fichiers.append(Path(dossier, nom).relative_to(racine).as_posix())
    return fichiers
