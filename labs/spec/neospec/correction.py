"""Boucle de correction bornée : écrire → valider → (si échec) renvoyer les erreurs au modèle."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from neospec import schemas
from neospec.generation import decisions_pour_modele, ecrire_artefacts
from neospec.llm import ClientLLM
from neospec.prompts import prompt
from neospec.validation import Rapport, valider_tout


@dataclass
class ResultatCorrection:
    ok: bool
    corrections: int                      # nombre d'appels de correction effectués
    rapport: Rapport                      # dernier rapport de validation
    generation: dict[str, Any]            # dernière génération (écrite sur disque)
    historique: list[dict[str, Any]] = field(default_factory=list)


def construire_message(generation: dict[str, Any], rapport: Rapport, decisions: dict[str, Any]) -> str:
    return (
        f"<rapport>\n{json.dumps({'erreurs': rapport.erreurs, 'avertissements': rapport.avertissements}, ensure_ascii=False, indent=1)}\n</rapport>\n\n"
        f"<decisions>{json.dumps(decisions_pour_modele(decisions), ensure_ascii=False)}</decisions>\n\n"
        f"<generation>{json.dumps(generation, ensure_ascii=False)}</generation>\n\n"
        "Corrige chaque erreur du rapport et renvoie la génération complète."
    )


def boucle_correction(client: ClientLLM, racine: Path, type_: str, decisions: dict[str, Any],
                      generation: dict[str, Any], max_corrections: int = 2,
                      ecrire: Callable[..., Any] = ecrire_artefacts,
                      valider: Callable[[Path, str], Rapport] = valider_tout) -> ResultatCorrection:
    """Écrit les artefacts, les valide, et tant que la validation échoue, demande une correction.

    - au plus `max_corrections` appels au modèle (étape « correction ») : la boucle est bornée ;
    - chaque correction est revalidée par le schéma local avant d'être écrite ;
    - l'historique garde, pour chaque tour, le nombre d'erreurs et d'avertissements ;
    - renvoie ok=False si la dernière validation échoue encore : l'humain reprend la main.
    """
    # TODO TP fil rouge : boucle écrire → valider → (si erreurs et corrections < max) client.json(etape='correction', ...) avec construire_message(generation, rapport, decisions), validation locale, historique par tour.
    raise NotImplementedError("TODO TP fil rouge : boucle_correction")
