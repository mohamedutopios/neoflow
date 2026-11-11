"""Routing : aiguiller une demande vers l'agent qui a les bons outils, les bons droits et le bon modèle.

Le routage déterministe (mots-clés) est gratuit, reproductible et auditable : c'est le défaut. Le classifieur
par LLM (`classifieur_llm`, modèle léger, sans outils) sert quand les demandes sont trop variées.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from neoagent.agent import Resultat
from neoagent.modele import MODELE_LEGER

REGLES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("revue", re.compile(r"\b(relis|relire|revue|review|diff à valider|vérifie le diff)\b", re.IGNORECASE)),
    ("tests", re.compile(r"\b(tests?|couverture|junit|vitest|scénarios? gherkin)\b", re.IGNORECASE)),
    ("exploration", re.compile(r"\b(où|explique|comment fonctionne|cherche|trouve|liste)\b", re.IGNORECASE)),
)


def classer(tache: str) -> str:
    """« revue », « tests », « exploration » ou « implementation » (défaut), par mots-clés."""
    for etiquette, motif in REGLES:
        if motif.search(tache):
            return etiquette
    return "implementation"


def classifieur_llm(client: Any, etiquettes: tuple[str, ...], defaut: str = "implementation") -> Callable[[str], str]:
    """Classifieur par un appel unique, sans outils (modèle léger conseillé : claude-haiku-5-5)."""

    def classifier(tache: str) -> str:
        systeme = ("Classez la demande dans exactement une de ces catégories et répondez par le seul mot : "
                   + ", ".join(etiquettes))
        reponse = client.creer(systeme, [{"role": "user", "content": tache}], [])
        mot = reponse.texte.strip().lower().split()[0] if reponse.texte.strip() else ""
        return mot if mot in etiquettes else defaut

    classifier.modele = getattr(client, "modele", MODELE_LEGER)  # type: ignore[attr-defined]
    return classifier


def router(tache: str, routes: dict[str, Callable[[str], Resultat]],
           classifieur: Callable[[str], str] = classer) -> tuple[str, Resultat]:
    etiquette = classifieur(tache)
    route = routes.get(etiquette) or routes.get("implementation")
    if route is None:
        raise KeyError(f"aucune route pour « {etiquette} » ni route par défaut « implementation »")
    return etiquette, route(tache)
