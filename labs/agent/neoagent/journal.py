"""Journal de trajectoire JSONL : une ligne par événement (contrat neoagent, lu par J10).

{"ts", "session", "etape", "type": "llm"|"tool_call"|"tool_result"|"approbation"|"erreur"|"fin",
 "outil", "entree", "sortie_extrait",
 "usage": {"input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"}, "modele"}

`usage` : celui de la réponse (`llm`) ou le cumul de la session (`fin`), tel que renvoyé par `response.usage`.
`cache_creation_input_tokens` (écriture en cache, facturée plus cher que l'entrée) est indispensable au calcul
du coût (J10) ; il vaut 0 en mode hors ligne.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TYPES = ("llm", "tool_call", "tool_result", "approbation", "erreur", "fin")
CHAMPS = ("ts", "session", "etape", "type", "outil", "entree", "sortie_extrait", "usage", "modele")
TAILLE_EXTRAIT = 500
CLES_USAGE = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def nouvelle_session() -> str:
    return uuid.uuid4().hex[:12]


class Journal:
    """Écrit les événements ; sans chemin, ne garde que la liste en mémoire (tests, workers)."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else None
        self.evenements: list[dict[str, Any]] = []
        self._verrou = threading.Lock()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def ecrire(self, type: str, *, session: str, etape: int, outil: str | None = None, entree: Any = None,
               sortie: str | None = None, usage: dict | None = None, modele: str | None = None) -> dict:
        if type not in TYPES:
            raise ValueError(f"type d'événement inconnu : {type}")
        evenement = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "session": session,
            "etape": etape,
            "type": type,
            "outil": outil,
            "entree": entree,
            "sortie_extrait": None if sortie is None else sortie[:TAILLE_EXTRAIT],
            "usage": None if usage is None else {cle: int(usage.get(cle, 0) or 0) for cle in CLES_USAGE},
            "modele": modele,
        }
        with self._verrou:
            self.evenements.append(evenement)
            if self.path:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(evenement, ensure_ascii=False, default=str) + "\n")
        return evenement


def lire_journal(path: Path | str) -> list[dict[str, Any]]:
    """Relit un journal JSONL (J10 : coûts, nombre d'appels, trajectoires)."""
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(ligne) for ligne in f if ligne.strip()]


def usage_total(evenements: list[dict[str, Any]]) -> dict[str, int]:
    """Somme de l'usage des appels au modèle (lignes `llm`).

    Ne sommez pas les lignes `fin` : une session poursuivie (Generator–Verifier) en écrit plusieurs, chacune avec
    l'usage cumulé depuis le début de la session.
    """
    total = dict.fromkeys(CLES_USAGE, 0)
    for evenement in evenements:
        if evenement.get("type") == "llm" and evenement.get("usage"):
            for cle in CLES_USAGE:
                total[cle] += int(evenement["usage"].get(cle, 0) or 0)  # anciens journaux : clé absente
    return total
