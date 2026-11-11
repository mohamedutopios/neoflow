"""Petites fonctions Git déterministes partagées par le lab (aucune dépendance externe).

Toutes les commandes passent par `subprocess.run(..., timeout=...)` : un `git` bloqué
est réellement tué, ce qui n'est pas le cas d'un thread Python qu'on abandonne.
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ErreurGit(RuntimeError):
    """Commande Git en échec (dépôt absent, révision inconnue...)."""


def git(depot: str | Path, *args: str, timeout: float = 20.0, ok_codes: tuple[int, ...] = (0,)) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(depot), *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:  # transformé en erreur transitoire par l'appelant
        raise TimeoutError(f"git {' '.join(args)} : délai de {timeout}s dépassé") from exc
    if proc.returncode not in ok_codes:
        raise ErreurGit(f"git {' '.join(args)} -> {proc.returncode} : {proc.stderr.strip()}")
    return proc.stdout


def racine_depot(chemin: str | Path) -> Path:
    return Path(git(chemin, "rev-parse", "--show-toplevel").strip())


def head(depot: str | Path) -> str:
    return git(depot, "rev-parse", "HEAD").strip()


def resoudre(depot: str | Path, rev: str) -> str:
    return git(depot, "rev-parse", "--verify", f"{rev}^{{commit}}").strip()


def contenu_a(depot: str | Path, commit: str, chemin: str) -> str | None:
    """Contenu d'un fichier à un commit donné (None s'il n'existe pas à ce commit)."""
    try:
        return git(depot, "show", f"{commit}:{chemin}")
    except ErreurGit:
        return None


def fichier_modifie_depuis(depot: str | Path, commit: str, chemin: str, cible: str = "HEAD") -> bool:
    """Vrai si `chemin` diffère entre `commit` et `cible` (ou a disparu)."""
    proc = subprocess.run(["git", "-C", str(depot), "diff", "--quiet", commit, cible, "--", chemin],
                          capture_output=True, timeout=20)
    if proc.returncode not in (0, 1):
        raise ErreurGit(f"git diff {commit} {cible} -- {chemin} : {proc.stderr.decode().strip()}")
    return proc.returncode == 1


@dataclass(frozen=True)
class Changement:
    statut: str            # A, M, D, R (renommage), C (copie), T (type)
    chemin: str            # chemin à la cible (nouveau chemin pour R)
    ancien_chemin: str | None = None


def changements(depot: str | Path, depuis: str, jusqu_a: str) -> list[Changement]:
    """`git diff --name-status -M` entre deux commits, sortie -z pour les noms exotiques."""
    brut = git(depot, "diff", "--name-status", "-M", "-z", depuis, jusqu_a)
    morceaux = [m for m in brut.split("\0") if m != ""]
    resultat: list[Changement] = []
    i = 0
    while i < len(morceaux):
        statut = morceaux[i][0]
        if statut in ("R", "C"):
            resultat.append(Changement(statut, morceaux[i + 2], morceaux[i + 1]))
            i += 3
        else:
            resultat.append(Changement(statut, morceaux[i + 1]))
            i += 2
    return resultat


def fichiers_suivis(depot: str | Path, commit: str) -> list[str]:
    return [l for l in git(depot, "ls-tree", "-r", "--name-only", commit).splitlines() if l]


def normaliser(texte: str) -> str:
    """Espaces de fin de ligne et lignes vides en bordure retirés ; indentation conservée."""
    lignes = [l.rstrip() for l in texte.splitlines()]
    while lignes and not lignes[0]:
        lignes.pop(0)
    while lignes and not lignes[-1]:
        lignes.pop()
    return "\n".join(lignes)


def empreinte(texte: str) -> str:
    return hashlib.sha256(normaliser(texte).encode("utf-8")).hexdigest()[:16]


def extrait(contenu: str, debut: int, fin: int) -> str:
    lignes = contenu.splitlines()
    return "\n".join(lignes[max(debut - 1, 0):fin])


def localiser(contenu: str, extrait_normalise: str) -> tuple[int, int] | None:
    """Retrouve un extrait (normalisé) dans un fichier, même s'il a été déplacé."""
    cible = extrait_normalise.splitlines()
    if not cible:
        return None
    lignes = [l.rstrip() for l in contenu.splitlines()]
    n = len(cible)
    for i in range(len(lignes) - n + 1):
        if lignes[i:i + n] == cible:
            return i + 1, i + n
    return None
