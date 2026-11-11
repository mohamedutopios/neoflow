"""ReAct : la boucle native de l'agent (raisonner, appeler un outil, observer le résultat).

Il n'y a rien à ajouter à `Agent` : la boucle tool use EST le pattern ReAct. Ce module existe pour que les
patterns se comparent à armes égales (même signature, même journal, mêmes bornes).
"""

from __future__ import annotations

from neoagent.agent import Agent, Resultat


def react(agent: Agent, tache: str) -> Resultat:
    return agent.executer(tache)
