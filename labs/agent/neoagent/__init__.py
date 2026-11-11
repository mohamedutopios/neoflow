"""neoagent : agent de développement NeoFlow codé avec l'API Claude (J04).

Contrat public (labs/agent/README.md, section Contrat), utilisé par les labs J05, J06, J09 et J10 :

    from neoagent import Agent, Approbateur, Journal, Politique, Tool, outils_de_base

    politique = Politique.generateur(Path("../neoflow-conges-back"))
    agent = Agent(outils_de_base(politique.racine, politique), journal=Journal("traj.jsonl"), offline=True)
    resultat = agent.executer("Implémente la tâche T04 du plan CONGES")
"""

from neoagent.agent import Agent, Resultat
from neoagent.approbation import Approbateur, Decision
from neoagent.garde_fous import Politique, RefusGardeFou
from neoagent.journal import Journal, lire_journal, usage_total
from neoagent.modele import ClientClaude, ModeleSimule, ReponseModele
from neoagent.sous_agents import outil_sous_agent
from neoagent.tools import Tool, outils_de_base

__all__ = [
    "Agent",
    "Approbateur",
    "ClientClaude",
    "Decision",
    "Journal",
    "ModeleSimule",
    "Politique",
    "RefusGardeFou",
    "ReponseModele",
    "Resultat",
    "Tool",
    "lire_journal",
    "outil_sous_agent",
    "outils_de_base",
    "usage_total",
]

__version__ = "1.0.0"
