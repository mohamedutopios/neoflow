"""Git worktrees : un worktree, une branche, un agent. Création séquentielle, travail parallèle.

Conventions (identiques au script du J4) : worktree `../<depot>-<nom>`, branche `feat/<nom>`.
L'humain fusionne ; neoagent ne pousse jamais et ne commite qu'après approbation.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from neoagent.approbation import Approbateur, Decision

NOM_VALIDE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


def git(repo: Path, *args: str, verifier: bool = True) -> str:
    fini = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if verifier and fini.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} : {fini.stderr.strip() or fini.stdout.strip()}")
    return fini.stdout.strip()


def racine_principale(repo: Path) -> Path:
    premiere = git(Path(repo), "worktree", "list", "--porcelain").splitlines()[0]
    return Path(premiere.removeprefix("worktree "))


def creer_worktree(repo: Path, nom: str, base: str = "HEAD", branche: str | None = None) -> Path:
    if not NOM_VALIDE.match(nom):
        raise ValueError(f"nom de worktree invalide : {nom!r} (minuscules, chiffres, tirets)")
    principal = racine_principale(Path(repo))
    chemin = principal.parent / f"{principal.name}-{nom}"
    branche = branche or f"feat/{nom}"
    if chemin.exists():
        raise FileExistsError(f"{chemin} existe déjà")
    existe = subprocess.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branche}"],
                            cwd=principal).returncode == 0
    if existe:
        git(principal, "worktree", "add", str(chemin), branche)
    else:
        git(principal, "worktree", "add", "-b", branche, str(chemin), base)
    return chemin


def supprimer_worktree(chemin: Path, *, force: bool = False, supprimer_branche: bool = False) -> None:
    chemin = Path(chemin)
    principal = racine_principale(chemin)
    branche = git(chemin, "branch", "--show-current", verifier=False)
    git(principal, "worktree", "remove", *(["--force"] if force else []), str(chemin))
    git(principal, "worktree", "prune")
    if supprimer_branche and branche:
        git(principal, "branch", "-D" if force else "-d", branche)


def diff_stat(chemin: Path) -> str:
    suivis = git(Path(chemin), "diff", "--stat", verifier=False)
    nouveaux = git(Path(chemin), "ls-files", "--others", "--exclude-standard", verifier=False)
    return suivis + (("\nnouveaux : " + ", ".join(nouveaux.splitlines())) if nouveaux else "")


def proposer_commit(chemin: Path, message: str, approbateur: Approbateur) -> Decision:
    """Commit après validation humaine du diff ; ne pousse jamais."""
    apercu = diff_stat(chemin) or "(aucun changement)"
    decision = approbateur.approuver(f"commit « {message} »", apercu)
    if decision.accordee and apercu != "(aucun changement)":
        git(Path(chemin), "add", "-A")
        git(Path(chemin), "commit", "-q", "-m", message)
    return decision
