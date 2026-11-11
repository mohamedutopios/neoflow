"""Rapport de validation : erreurs (bloquantes), avertissements, informations."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Rapport:
    erreurs: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)

    def erreur(self, message: str) -> None:
        self.erreurs.append(message)

    def avertir(self, message: str) -> None:
        self.avertissements.append(message)

    def info(self, message: str) -> None:
        self.infos.append(message)

    @property
    def ok(self) -> bool:
        return not self.erreurs

    def texte(self, titre: str = "Validation") -> str:
        lignes = [titre, ""]
        lignes += [f"  ✔ {m}" for m in self.infos]
        lignes += [f"  ⚠ {m}" for m in self.avertissements]
        lignes += [f"  ✖ {m}" for m in self.erreurs]
        lignes += ["", f"{len(self.erreurs)} erreur(s), {len(self.avertissements)} avertissement(s).",
                   "Porte déterministe franchie : la relecture humaine peut commencer." if self.ok
                   else "Porte déterministe NON franchie."]
        return "\n".join(lignes)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "erreurs": self.erreurs, "avertissements": self.avertissements, "infos": self.infos}
