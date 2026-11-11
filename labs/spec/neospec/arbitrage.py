"""Étape 2 — arbitrage humain : chaque question reçoit une décision tracée (porte 1).

Fichier de réponses (YAML) :

    decideur: Sophie Garnier (DRH)          # décideur par défaut
    date: 2026-11-16
    decisions:
      Q-01: valider                          # l'hypothèse proposée est validée telle quelle
      Q-02:
        decision: remplacer                  # l'humain réécrit l'hypothèse
        hypothese: "Le premier jour peut commencer l'après-midi…"
        decideur: Sophie Garnier (DRH)       # facultatif, sinon décideur par défaut
      Q-07:
        decision: rejeter
        motif: "Hors périmètre v1"
    ajouts:                                  # questions vues après coup (pair, VARIANTES.md)
      - question: "Durée maximale d'une demande ?"
        source: "VARIANTES (R5, non vu)"
        priorite: Importante
        decision: "20 jours ouvrés"
        hypothese: "Une demande ne dépasse pas 20 jours ouvrés."   # facultatif
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any, Callable

import yaml

DECISIONS = ("valider", "remplacer", "rejeter")
AUTEURS_INTERDITS = re.compile(r"\b(agent|claude|modèle|modele|neospec|ia|llm)\b", re.I)


class PorteNonFranchie(RuntimeError):
    def __init__(self, manquantes: list[str], problemes: list[str]):
        details = []
        if manquantes:
            details.append("questions sans décision : " + ", ".join(manquantes))
        details += problemes
        super().__init__("Porte 1 non franchie — " + " ; ".join(details))
        self.manquantes = manquantes
        self.problemes = problemes


def charger_reponses(chemin: Path) -> dict[str, Any]:
    return yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}


def _numero(identifiant: str) -> int:
    return int(identifiant.split("-")[1])


def appliquer_reponses(questions: dict[str, Any], reponses: dict[str, Any]) -> dict[str, Any]:
    """Construit le dossier de décisions à partir des questions et des réponses humaines.

    Pour chaque question :
    - sans réponse : decision None, hypothèse « À valider » (la porte 1 la refusera) ;
    - « valider » : hypothèse proposée, statut « Validée » ;
    - « remplacer » : hypothèse réécrite (clé `hypothese` obligatoire), statut « Validée » ;
    - « rejeter » : statut « Rejetée », décision = motif ;
    chaque hypothèse tranchée porte son décideur (réponse ou défaut) et la date.
    Les `ajouts` reçoivent les numéros suivants (Q-xx, et H-xx s'ils portent une hypothèse).
    Lève ValueError sur une décision inconnue ou un « remplacer » sans hypothèse.
    """
    # TODO TP1 : parcourir questions['questions'], appliquer valider / remplacer / rejeter, tracer décideur et date, numéroter les ajouts à la suite.
    raise NotImplementedError("TODO TP1 : appliquer_reponses")


def _q(q: dict[str, Any]) -> dict[str, Any]:
    return {k: q[k] for k in ("id", "question", "source", "priorite")}


def verifier_porte_1(decisions: dict[str, Any]) -> None:
    """Porte 1, déterministe : aucune génération tant qu'une question n'a pas de décision humaine.

    Refuse aussi : une hypothèse tranchée sans décideur ou sans date, un décideur qui n'est pas
    un humain (« agent », « Claude », « modèle »…), une hypothèse encore « À valider ».
    Lève PorteNonFranchie.
    """
    # TODO TP1 : lister les questions sans décision et les hypothèses non tranchées ou sans décideur humain, lever PorteNonFranchie.
    raise NotImplementedError("TODO TP1 : verifier_porte_1")


def arbitrer_interactif(questions: dict[str, Any], decideur: str, date: str | None = None,
                        entree: Callable[[str], str] = input, ecrire: Callable[[str], None] = print) -> dict[str, Any]:
    """Pose chaque question dans le terminal : [v]alider, [r]emplacer, re[j]eter."""
    decisions: dict[str, Any] = {}
    for q in questions["questions"]:
        ecrire(f"\n{q['id']} [{q['priorite']}] {q['question']}\n  source : {q['source']}\n"
               f"  hypothèse proposée ({q['hypothese']['id']}) : {q['hypothese']['enonce']}")
        while True:
            choix = entree("  [v]alider, [r]emplacer, re[j]eter ? ").strip().lower()[:1]
            if choix == "v":
                decisions[q["id"]] = "valider"
            elif choix == "r":
                decisions[q["id"]] = {"decision": "remplacer", "hypothese": entree("  nouvelle hypothèse : ")}
            elif choix == "j":
                decisions[q["id"]] = {"decision": "rejeter", "motif": entree("  motif : ") or "Rejetée"}
            else:
                continue
            break
    return appliquer_reponses(questions, {"decideur": decideur, "date": date, "decisions": decisions})
