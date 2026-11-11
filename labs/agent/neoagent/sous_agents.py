"""Sous-agent exposé comme un outil : l'agent principal délègue une sous-tâche à un agent neuf.

- contexte isolé : le sous-agent démarre avec un historique vide et ne renvoie qu'un rapport ;
- droits distincts : sa politique et ses outils sont ceux de la fabrique (ex. rédacteur de tests) ;
- bornes propres : max_etapes, budget ; son usage est remonté dans le rapport pour la mesure.

C'est l'équivalent, en code, de la délégation d'un assistant à ses sous-agents (outil task d'OpenCode).
"""

from __future__ import annotations

from typing import Callable

from neoagent.agent import Agent
from neoagent.tools import Tool

CONSIGNE = ("Vous êtes un sous-agent. Réalisez uniquement la sous-tâche ci-dessous, puis répondez par un rapport "
            "court et factuel (fichiers, résultats, questions). Le demandeur ne voit que ce rapport.\n\n")


def outil_sous_agent(nom: str, description: str, fabrique: Callable[[], Agent],
                     risque: str = "ecriture") -> Tool:
    """La description fait la délégation : dites quoi, quand, et quand ne pas utiliser ce sous-agent."""

    def deleguer(entree: dict) -> str:
        resultat = fabrique().executer(CONSIGNE + entree["consigne"])
        return (f"[sous-agent {nom} : {resultat.statut}, {resultat.etapes} étapes, {resultat.tokens} tokens, "
                f"outils {', '.join(resultat.appels_outils) or 'aucun'}]\n{resultat.reponse}")

    return Tool(nom, description,
                {"type": "object", "properties": {"consigne": {"type": "string",
                                                               "description": "sous-tâche complète et autonome"}},
                 "required": ["consigne"], "additionalProperties": False},
                deleguer, risque=risque)  # type: ignore[arg-type]
