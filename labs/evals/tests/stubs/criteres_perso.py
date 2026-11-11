"""Exemple de module --criteres-externes (ce que le stagiaire écrit au TP2)."""


def pas_de_boucle(crit, ctx):
    if ctx.trajectoire is None:
        return None, "pas de journal"
    vus = {}
    for a in ctx.trajectoire.appels:
        cle = (a.outil, a.texte_entree())
        vus[cle] = vus.get(cle, 0) + 1
    pire = max(vus.values(), default=0)
    return pire < int(crit.get("max_repetitions", 3)), f"appel identique répété au plus {pire} fois"


CRITERES = {"pas_de_boucle": pas_de_boucle}
