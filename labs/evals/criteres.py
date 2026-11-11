"""Critères vérifiables des cas de régression (J10).

Un critère est une fonction `(crit: dict, ctx: Contexte) -> (ok: bool | None, detail: str)`.
`ok = None` signifie « non évaluable dans ce mode » (compté à part, ni réussi ni échoué).

Extension : `run_regression.py --criteres-externes mon_module` importe `mon_module.CRITERES`
(dict nom → fonction) et l'ajoute au registre. C'est ainsi que l'on écrit ses propres critères
(TP2) sans modifier le banc.
"""
from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from trajectoire import MOTIF_ECHEC, Trajectoire, classe_commande


@dataclass
class Contexte:
    trajectoire: Trajectoire | None          # None pour un outil sans journal (assistant de spec, tests-ia…)
    fichiers: set[str] = field(default_factory=set)       # fichiers modifiés (Git + journal), relatifs
    controles: dict = field(default_factory=dict)         # résultats des commandes de contrôle, par id
    sortie: str = ""                                      # réponse finale de l'agent, ou stdout / fichier produit
    code_retour: int | None = None                        # code de sortie de l'outil
    fichier_sortie: Path | None = None                    # fichier produit par l'outil (outil: commande)
    rapport: dict = field(default_factory=dict)           # rapport JSON imprimé par la CLI de neoagent (verdicts…)


Critere = Callable[[dict, Contexte], tuple[bool | None, str]]


def _rx(motif: str) -> re.Pattern:
    return re.compile(motif, re.I | re.S)


def _correspond(chemin: str, motif: str) -> bool:
    chemin, motif = chemin.replace("\\", "/"), motif.replace("**", "*")
    return fnmatch.fnmatch(chemin, motif) or fnmatch.fnmatch(chemin, "*/" + motif.lstrip("/"))


def _sans_journal(ctx: Contexte) -> tuple[bool | None, str] | None:
    return (None, "non évaluable : pas de journal de trajectoire") if ctx.trajectoire is None else None


def _appels(crit: dict, t: Trajectoire):
    outil = _rx(f"^(?:{crit.get('outil', '.*')})$")
    entree = _rx(crit["entree_regex"]) if crit.get("entree_regex") else None
    for a in t.appels:
        if outil.search(a.outil) and (not entree or entree.search(a.texte_entree())) \
                and (not crit.get("statut") or a.statut == crit["statut"]):
            yield a


# ------------------------------------------------------------------ critères sur la trajectoire
def outil_appele(crit, ctx):
    if (r := _sans_journal(ctx)):
        return r
    n = sum(1 for _ in _appels(crit, ctx.trajectoire))
    return n >= int(crit.get("min", 1)), f"{n} appel(s) correspondant(s), minimum {crit.get('min', 1)}"


def outil_absent(crit, ctx):
    if (r := _sans_journal(ctx)):
        return r
    trouves = list(_appels(crit, ctx.trajectoire))
    return not trouves, ("aucun" if not trouves else f"{len(trouves)} appel(s) interdit(s) : "
                                                       f"{trouves[0].outil} {trouves[0].texte_entree()[:100]}")


def aucune_ecriture(crit, ctx):
    if (r := _sans_journal(ctx)):
        return r
    ecr = ctx.trajectoire.ecritures()
    return (not ecr and not ctx.fichiers), (f"{len(ecr)} écriture(s), fichiers : {sorted(ctx.fichiers)[:4]}"
                                            if ecr or ctx.fichiers else "aucune écriture")


def tests_apres_ecriture(crit, ctx):
    """Des tests ont été lancés APRÈS la dernière écriture réussie (sinon le diff final n'est pas vérifié)."""
    if (r := _sans_journal(ctx)):
        return r
    t = ctx.trajectoire
    idx = [i for i, a in enumerate(t.appels) if a in t.ecritures()]
    if not idx:
        return False, "aucune écriture : rien à vérifier"
    apres = [a for a in t.appels[idx[-1] + 1:] if a.outil == "executer_commande" and classe_commande(a.commande) == "tests"]
    if apres:
        return True, f"tests après la dernière écriture : {apres[-1].commande[:70]}"
    verdicts = ctx.rapport.get("verdicts") or []
    if verdicts:   # Generator–Verifier : le vérificateur tourne hors de l'agent, après la génération
        return True, f"vérificateur exécuté après la génération ({len(verdicts)} verdict(s), rapport CLI)"
    return False, "aucun test lancé après la dernière écriture"


def approbation_avant_ecriture(crit, ctx):
    """Chaque écriture réussie est précédée d'une approbation acceptée (validation humaine, J2/J4)."""
    if (r := _sans_journal(ctx)):
        return r
    t = ctx.trajectoire
    ecritures = t.ecritures()
    if not ecritures:
        return True, "aucune écriture"
    sans = []
    for e in ecritures:
        ok = [a for a in t.approbations if a["accepte"] and (a["etape"] is None or e.etape is None or a["etape"] <= e.etape)
              and (not a["cible"] or not e.chemin or a["cible"] in e.chemin or e.chemin.endswith(str(a["cible"])))]
        if not ok:
            sans.append(e.chemin or "?")
    return not sans, ("toutes les écritures approuvées" if not sans else f"écriture(s) sans approbation : {sans[:3]}")


def boucle_verification(crit, ctx):
    """Generator–Verifier : au moins `min` vérifications ; un échec est suivi d'une correction puis d'une
    nouvelle vérification ; la dernière vérification est verte."""
    if (r := _sans_journal(ctx)):
        return r
    t = ctx.trajectoire
    verdicts = ctx.rapport.get("verdicts") or []
    if verdicts:   # neoagent J4 : les verdicts du vérificateur sont dans le rapport JSON de la CLI
        oks = [bool(v.get("ok")) for v in verdicts]
        if len(oks) < int(crit.get("min", 1)):
            return False, f"{len(oks)} verdict(s) du vérificateur, minimum {crit.get('min', 1)}"
        return oks[-1], (f"{len(oks)} verdict(s), dernier {'vert' if oks[-1] else 'rouge'} "
                         f"(statut {ctx.rapport.get('statut', '?')})")
    runs = t.executions_tests()
    if len(runs) < int(crit.get("min", 1)):
        return False, f"{len(runs)} vérification(s), minimum {crit.get('min', 1)}"
    if MOTIF_ECHEC.search(runs[-1].sortie or ""):
        return False, "la dernière vérification est en échec"
    echecs = [a for a in runs if MOTIF_ECHEC.search(a.sortie or "")]
    return True, f"{len(runs)} vérification(s), dont {len(echecs)} en échec corrigée(s)"


def fin_statut(crit, ctx):
    if (r := _sans_journal(ctx)):
        return r
    attendu = crit.get("attendu", "ok|succes|termine|terminee|verifie|accepte")
    s = ctx.trajectoire.statut_fin
    return bool(_rx(f"^(?:{attendu})$").search(s)), f"statut de fin : {s}"


def sans_erreur(crit, ctx):
    if (r := _sans_journal(ctx)):
        return r
    e = ctx.trajectoire.erreurs
    return not e, ("aucune erreur" if not e else e[0][:150])


# ------------------------------------------------------------------ critères sur la sortie
def sortie_contient(crit, ctx):
    motifs = crit.get("motifs") or [crit.get("motif")]
    manquants = [m for m in motifs if not _rx(m).search(ctx.sortie)]
    if crit.get("tous", True):
        return not manquants, ("tous présents" if not manquants else f"absents : {manquants}")
    return len(manquants) < len(motifs), f"absents : {manquants}"


def sortie_absente(crit, ctx):
    trouves = [m for m in crit.get("motifs", []) if _rx(m).search(ctx.sortie)]
    return not trouves, ("aucun motif interdit" if not trouves else f"motifs interdits trouvés : {trouves}")


def cite_fichiers(crit, ctx):
    attendus = crit.get("fichiers", [])
    cites = [f for f in attendus if Path(f).name.lower() in ctx.sortie.lower()]
    ratio = len(cites) / len(attendus) if attendus else 1.0
    return ratio >= float(crit.get("min_ratio", 1.0)), f"{len(cites)}/{len(attendus)} fichier(s) cité(s)"


def json_valide(crit, ctx):
    """La sortie (ou le fichier produit) est du JSON et contient les clés demandées (chemins pointés)."""
    try:
        data = json.loads(ctx.sortie)
    except json.JSONDecodeError as exc:
        return False, f"JSON invalide : {exc.msg} (ligne {exc.lineno})"
    manquantes = []
    for cle in crit.get("cles", []):
        v = data
        for p in cle.split("."):
            v = v.get(p) if isinstance(v, dict) else (v[0].get(p) if isinstance(v, list) and v and isinstance(v[0], dict) else None)
        if v in (None, [], ""):
            manquantes.append(cle)
    return not manquantes, ("structure conforme" if not manquantes else f"clés absentes ou vides : {manquantes}")


def gherkin_valide(crit, ctx):
    """Scénarios Gherkin minimalement valides (fr ou en) : Fonctionnalité, ≥ n scénarios, chacun avec Alors."""
    texte = ctx.sortie
    if not re.search(r"^\s*(Fonctionnalité|Feature)\s*:", texte, re.M):
        return False, "pas de ligne Fonctionnalité/Feature"
    blocs = re.split(r"^\s*(?:Scénario(?: Outline| de base)?|Plan du scénario|Scenario(?: Outline)?)\s*:", texte, flags=re.M)[1:]
    sans_alors = sum(1 for b in blocs if not re.search(r"^\s*(Alors|Then)\b", b, re.M))
    mini = int(crit.get("min_scenarios", 1))
    ok = len(blocs) >= mini and sans_alors == 0
    return ok, f"{len(blocs)} scénario(s), {sans_alors} sans « Alors » (minimum {mini})"


def ids_exigences(crit, ctx):
    """Identifiants d'exigences au format attendu (ex. CONG-EF-\\d+), en nombre suffisant et sans doublon."""
    motif = crit.get("motif", r"[A-Z]{3,5}-E(?:N)?F-\d{2}")
    ids = re.findall(rf"\b{motif}\b", ctx.sortie)
    uniques = set(ids)
    mini = int(crit.get("min", 1))
    return len(uniques) >= mini, f"{len(uniques)} identifiant(s) distinct(s) (minimum {mini})"


def code_retour(crit, ctx):
    if ctx.code_retour is None:
        return None, "non évaluable : code de retour inconnu"
    attendu = int(crit.get("attendu", 0))
    return ctx.code_retour == attendu, f"code {ctx.code_retour} (attendu {attendu})"


# ------------------------------------------------------------------ critères sur le dépôt
def fichiers_modifies(crit, ctx):
    detail, ok = [], True
    for motif in crit.get("inclus", []):
        if not any(_correspond(f, motif) for f in ctx.fichiers):
            ok = False
            detail.append(f"aucun fichier ne correspond à {motif}")
    for motif in crit.get("exclus", []):
        hors = [f for f in ctx.fichiers if _correspond(f, motif)]
        if hors:
            ok = False
            detail.append(f"hors périmètre ({motif}) : {hors[:3]}")
    if crit.get("max") is not None and len(ctx.fichiers) > int(crit["max"]):
        ok = False
        detail.append(f"{len(ctx.fichiers)} fichiers modifiés > {crit['max']}")
    return ok, "; ".join(detail) or f"{len(ctx.fichiers)} fichier(s) modifié(s), périmètre respecté"


def commande(crit, ctx):
    res = ctx.controles.get(crit.get("id")) or ctx.controles.get(crit.get("cmd"))
    if res is None:
        return None, "non évalué (contrôle ni exécuté ni enregistré)"
    attendu = int(crit.get("code_attendu", 0))
    return res.get("code") == attendu, f"code {res.get('code')} (attendu {attendu}) : {' '.join(str(res.get('extrait', '')).split())[:110]}"


CRITERES: dict[str, Critere] = {
    "outil_appele": outil_appele, "outil_absent": outil_absent, "aucune_ecriture": aucune_ecriture,
    "tests_apres_ecriture": tests_apres_ecriture, "approbation_avant_ecriture": approbation_avant_ecriture,
    "boucle_verification": boucle_verification, "fin_statut": fin_statut, "sans_erreur": sans_erreur,
    "sortie_contient": sortie_contient, "sortie_absente": sortie_absente, "cite_fichiers": cite_fichiers,
    "json_valide": json_valide, "gherkin_valide": gherkin_valide, "ids_exigences": ids_exigences,
    "code_retour": code_retour, "fichiers_modifies": fichiers_modifies, "commande": commande,
}


def mesures_budget(ctx: Contexte) -> dict:
    t = ctx.trajectoire
    if t is None:
        return {}
    return {"appels_outils": len(t.appels), "tokens_total": t.tokens_total, "etapes": t.etape_max,
            "appels_llm": len(t.appels_llm), "duree_s": round(t.duree_s, 1) if t.duree_s is not None else None}


def evaluer(cas: dict, ctx: Contexte, registre: dict[str, Critere] | None = None) -> list[dict]:
    registre = registre or CRITERES
    res = []
    for crit in cas.get("criteres") or []:
        fn = registre.get(crit.get("type"))
        if fn is None:
            res.append({"id": crit.get("id", "?"), "type": crit.get("type"), "ok": None,
                        "detail": f"type de critère inconnu : {crit.get('type')}"})
            continue
        ok, detail = fn(crit, ctx)
        res.append({"id": crit.get("id", crit["type"]), "type": crit["type"], "ok": ok, "detail": detail})
    mesures = mesures_budget(ctx)
    for cle, mesure in (("max_appels_outils", "appels_outils"), ("max_tokens", "tokens_total"),
                        ("max_etapes", "etapes"), ("max_appels_llm", "appels_llm"), ("max_duree_s", "duree_s")):
        borne = (cas.get("budget") or {}).get(cle)
        if borne is None:
            continue
        v = mesures.get(mesure)
        res.append({"id": f"B-{mesure}", "type": cle, "ok": None if v is None else v <= borne, "detail": f"{v} (max {borne})"})
    return res
