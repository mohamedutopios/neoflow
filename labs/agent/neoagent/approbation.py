"""Validation humaine avant écriture, exécution et commit.

Trois modes :
- « interactif » : la décision est demandée dans le terminal (aperçu du diff ou de la commande) ;
- « refus »      : tout est refusé (défaut sûr, mode non interactif, CI) ;
- « accord »     : tout est accordé (tests automatisés, sandbox jetable uniquement).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Callable, Literal

Mode = Literal["interactif", "refus", "accord"]


@dataclass(frozen=True)
class Decision:
    accordee: bool
    motif: str


@dataclass
class Approbateur:
    mode: Mode = "refus"
    risques: frozenset[str] = frozenset({"ecriture", "execution"})
    entree: Callable[[str], str] = field(default=input, repr=False)
    sortie: Callable[[str], None] = field(default=lambda texte: print(texte, file=sys.stderr), repr=False)

    def __post_init__(self) -> None:
        if self.mode not in ("interactif", "refus", "accord"):
            raise ValueError(f"mode d'approbation inconnu : {self.mode!r}")

    def doit_demander(self, risque: str) -> bool:
        return risque in self.risques

    def approuver(self, objet: str, detail: str) -> Decision:
        if self.mode == "accord":
            return Decision(True, "accord automatique (mode accord)")
        if self.mode == "refus":
            return Decision(False, "refus automatique (mode refus : aucune validation humaine possible)")
        self.sortie(f"\n=== Validation demandée : {objet} ===\n{detail}\n")
        reponse = self.entree("Accorder ? [o/N] ").strip().lower()
        if reponse in ("o", "oui", "y", "yes"):
            return Decision(True, "accordé par l'humain")
        return Decision(False, "refusé par l'humain" + (f" : {reponse}" if reponse not in ("", "n", "non") else ""))
