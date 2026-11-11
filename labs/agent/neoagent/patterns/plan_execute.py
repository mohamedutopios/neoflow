"""Plan-and-Execute : un planificateur en lecture seule propose un plan JSON, l'humain le valide, un exécutant
neuf (contexte isolé) réalise chaque étape. Arrêt à la première étape qui échoue."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

from neoagent.agent import Agent, Resultat
from neoagent.approbation import Approbateur

CONSIGNE_PLAN = """Produisez un plan d'exécution pour la tâche ci-dessous, SANS rien modifier.
Terminez votre réponse par un tableau JSON, et rien après :
[{"etape": "description courte et vérifiable", "fichiers": ["chemin", ...], "verification": "commande"}]

Tâche : """


@dataclass
class EtapePlan:
    etape: str
    fichiers: list[str] = field(default_factory=list)
    verification: str = ""


@dataclass
class ResultatPlan:
    statut: str  # "termine", "plan_refuse", "plan_invalide", "echec_etape"
    plan: list[EtapePlan]
    resultats: list[Resultat]
    planification: Resultat


def extraire_plan(texte: str) -> list[EtapePlan]:
    """Dernier tableau JSON du texte ; lève ValueError s'il est absent ou mal formé."""
    candidats = re.findall(r"\[\s*\{.*?\}\s*\]", texte, flags=re.DOTALL)
    if not candidats:
        raise ValueError("aucun plan JSON trouvé dans la réponse du planificateur")
    donnees = json.loads(candidats[-1])
    return [EtapePlan(d["etape"], list(d.get("fichiers", [])), d.get("verification", "")) for d in donnees]


def plan_execute(planificateur: Agent, fabrique_executant: Callable[[], Agent], tache: str,
                 approbateur: Approbateur) -> ResultatPlan:
    planification = planificateur.executer(CONSIGNE_PLAN + tache)
    try:
        plan = extraire_plan(planification.reponse)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        return ResultatPlan("plan_invalide", [], [], Resultat(planification.statut, str(exc), planification.etapes,
                                                            planification.usage, planification.session))
    rendu = "\n".join(f"{i}. {e.etape}  [{', '.join(e.fichiers)}]  → {e.verification}" for i, e in enumerate(plan, 1))
    decision = approbateur.approuver("plan d'exécution", rendu)
    planificateur.journal.ecrire("approbation", session=planification.session, etape=planification.etapes,
                                 outil="plan_execute", entree={"accordee": decision.accordee, "plan": rendu},
                                 sortie=decision.motif, modele=planificateur.modele)
    if not decision.accordee:
        return ResultatPlan("plan_refuse", plan, [], planification)
    resultats: list[Resultat] = []
    for numero, etape in enumerate(plan, 1):
        consigne = (f"Tâche globale : {tache}\nÉtape {numero}/{len(plan)} du plan validé : {etape.etape}\n"
                    f"Fichiers prévus : {', '.join(etape.fichiers) or 'à déterminer'}\n"
                    f"Vérification attendue : {etape.verification or 'tests du module'}\n"
                    "Ne réalisez que cette étape.")
        resultat = fabrique_executant().executer(consigne)
        resultats.append(resultat)
        if not resultat.ok:
            return ResultatPlan("echec_etape", plan, resultats, planification)
    return ResultatPlan("termine", plan, resultats, planification)
