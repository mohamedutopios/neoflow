"""Generator–Verifier : le générateur (agent) produit, le vérificateur (code : Maven, Vitest, script de
périmètre) juge, le générateur reçoit un retour ciblé. Au plus `max_tours` ; au-delà, l'humain requalifie
(spécification ambiguë, test faux ou code).

Le générateur ne se valide jamais lui-même : son rapport (« tous les tests passent ») n'entre pas dans le
verdict. Seul le vérificateur décide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from neoagent.agent import Agent, Resultat
from neoagent.verificateurs import Verdict, Verificateur

RETOUR = """Le vérificateur déterministe est ROUGE (tour {tour}/{max_tours}).
Commande : {commande} (code retour {code})
Extrait de la sortie :
{extrait}

Corrigez le code de production pour satisfaire ce vérificateur. Ne modifiez, ne supprimez, ne désactivez aucun test.
Si vous pensez que le test est faux, arrêtez-vous et expliquez pourquoi, avec la référence de la spécification."""


@dataclass
class ResultatGV:
    statut: str  # "verifie", "echec_verification", "arret_generateur"
    tours: int
    verdicts: list[Verdict] = field(default_factory=list)
    resultats: list[Resultat] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.statut == "verifie"


# TODO-J04 generator-verifier : générez, vérifiez, renvoyez l'extrait d'échec au générateur, au plus max_tours — TP 2, étape 2
def generator_verifier(agent: Agent, tache: str, verificateur: Verificateur, worktree: Path,
                       max_tours: int = 3) -> ResultatGV:
    """Génère (`agent.executer`), vérifie (`verificateur(worktree)`), renvoie l'extrait d'échec au MÊME agent
    (`agent.poursuivre(RETOUR.format(...))`), au plus `max_tours` vérifications.

    Statuts : « verifie » (un verdict vert), « echec_verification » (max_tours verdicts rouges),
    « arret_generateur » (le générateur s'est arrêté sur une borne : on ne vérifie pas un état inconnu).
    """
    raise NotImplementedError("TODO-J04 generator-verifier : générez, vérifiez, renvoyez l'extrait d'échec au générateur, au plus max_tours — TP 2, étape 2")
