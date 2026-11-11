"""Patterns agentiques codés au-dessus de `Agent` : du plus simple au plus coûteux.

react               la boucle native : penser, agir, observer
plan_execute        un planificateur en lecture seule, un plan validé par l'humain, un exécutant par étape
routing             une demande, un aiguillage déterministe (ou un classifieur léger), un agent spécialisé
generator_verifier  un générateur, un vérificateur déterministe (Maven), un retour ciblé, au plus N tours
evaluator_optimizer un critère mesurable, une critique, une nouvelle version, jusqu'au seuil
orchestrator_workers des sous-tâches indépendantes, un worktree et un contexte isolé par worker, en parallèle
"""

from neoagent.patterns.evaluator_optimizer import Evaluation, evaluateur_tracabilite, evaluator_optimizer
from neoagent.patterns.generator_verifier import ResultatGV, generator_verifier
from neoagent.patterns.orchestrator_workers import ResultatWorker, SousTache, orchestrer
from neoagent.patterns.plan_execute import EtapePlan, extraire_plan, plan_execute
from neoagent.patterns.react import react
from neoagent.patterns.routing import classer, router

__all__ = [
    "EtapePlan", "Evaluation", "ResultatGV", "ResultatWorker", "SousTache", "classer", "evaluateur_tracabilite",
    "evaluator_optimizer", "extraire_plan", "generator_verifier", "orchestrer", "plan_execute", "react", "router",
]
