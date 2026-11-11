"""Rendu déterministe des artefacts : le modèle fournit des données, le code écrit les fichiers.

Le format produit est celui des gabarits J03 (SPEC_TEMPLATE, MATRICE, PLAN, ADR), lu par la
validation (titres « ### EF-01 — … », lignes « | H-01 | … | Validée | … »).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from neospec import config


class EcritureInterdite(PermissionError):
    pass


def chemin_autorise(racine: Path, chemin: Path) -> Path:
    """Garde-fou J2 : refuse toute écriture hors des zones autorisées du dépôt."""
    racine = racine.resolve()
    cible = (chemin if chemin.is_absolute() else racine / chemin).resolve()
    for zone in config.ZONES_ECRITURE:
        base = (racine / zone).resolve()
        if cible == base or base in cible.parents:
            return cible
    raise EcritureInterdite(f"Écriture refusée hors de {', '.join(config.ZONES_ECRITURE)} : {cible}")


def _cell(texte: Any) -> str:
    return str(texte if texte not in (None, "") else "—").replace("|", "\\|").replace("\n", " ").strip()


def _table(entetes: list[str], lignes: list[list[Any]]) -> str:
    out = ["| " + " | ".join(entetes) + " |", "|" + "---|" * len(entetes)]
    out += ["| " + " | ".join(_cell(c) for c in ligne) + " |" for ligne in lignes]
    return "\n".join(out)


def operations_delta(openapi_yaml: str) -> list[list[str]]:
    try:
        spec = yaml.safe_load(openapi_yaml) or {}
    except yaml.YAMLError:
        return [["(contrat illisible)", "—", "—"]]
    lignes = []
    for chemin, item in (spec.get("paths") or {}).items():
        for methode, op in (item or {}).items():
            if methode in ("get", "put", "post", "delete", "patch") and isinstance(op, dict):
                lignes.append([f"`{methode.upper()} {chemin}`", op.get("x-neoflow-delta", "—"),
                               ", ".join(op.get("x-exigences") or []) or "—"])
    return lignes


def rendre_spec(type_: str, decisions: dict[str, Any], g: dict[str, Any], statut: str = "EN REVUE",
                adr: str | None = None) -> str:
    s = config.slug(type_)
    decideurs = sorted({h["valide_par"] for h in decisions["hypotheses"] if h.get("valide_par")})
    p: list[str] = [
        f"# Spécification — {type_} : {g['titre']}",
        "",
        _table(["Champ", "Valeur"], [
            ["Identifiant", f"SPEC-{type_}"],
            ["Ticket source", f"`docs/tickets/{type_}.md` ({decisions.get('ticket') or '?'})"],
            ["Statut", statut],
            ["Version", "0.3"],
            ["Rédaction", "Assistant de spécification `neospec` (lab J03), relu par le stagiaire"],
            ["Validation des hypothèses", f"{', '.join(decideurs) or '—'}, le {decisions.get('date')}"],
            ["Relecture", "En attente (porte 3)"],
            ["Artefacts liés", f"`docs/specs/{s}/features/`, `docs/specs/{s}/openapi/{s}-delta.yaml`, "
                               f"{('`' + adr + '`, ') if adr else ''}`docs/specs/{s}/PLAN_TACHES.md`, "
                               f"`docs/specs/{s}/MATRICE_TRACABILITE.md`"],
        ]),
        "",
        "Cycle de vie du statut : `BROUILLON` → `HYPOTHÈSES VALIDÉES` → `EN REVUE` → `PRÊTE`. "
        "Seul un humain passe la spécification à `PRÊTE` (porte 4) ; l'assistant ne l'écrit jamais.",
        "",
        "---",
        "",
        "## 1. Contexte et objectif",
        "",
        g["contexte"],
        "",
        "## 2. User stories",
        "",
        _table(["Id", "Story", "Contrôle INVEST"], [[u["id"], u["story"], u["invest"]] for u in g["user_stories"]]),
        "",
        "## 3. Périmètre — non-objectifs",
        "",
        _table(["Id", "Non-objectif", "Raison"], [[n["id"], n["objectif"], n["raison"]] for n in g["non_objectifs"]]),
        "",
        "## 4. Questions et décisions",
        "",
        _table(["Id", "Question", "Source", "Priorité", "Décision", "Hypothèse"],
               [[q["id"], q["question"], q["source"], q["priorite"], q.get("decision"), q.get("hypothese")]
                for q in decisions["questions"]]),
        "",
        "## 5. Hypothèses",
        "",
        _table(["Id", "Hypothèse", "Statut", "Validée par", "Date"],
               [[h["id"], h["enonce"], h["statut"], h.get("valide_par"), h.get("date")] for h in decisions["hypotheses"]]),
        "",
        "## 6. Règles métier",
        "",
        "Chaque refus est renvoyé dans un ProblemDetail 422 ; chaque message commence par son code, suivi de ` : `.",
        "",
        _table(["Id", "Règle", "Code d'erreur", "Exemple de message"],
               [[r["id"], r["regle"], f"`{r['code']}`" if r["code"] else "— (calcul)", r["exemple"]] for r in g["regles"]]),
        "",
        "## 7. Exigences fonctionnelles",
        "",
    ]
    for e in g["exigences"]:
        regles = f" ({', '.join(e['regles'])})" if e["regles"] else ""
        p += [f"### {e['id']} — {e['titre']}", "", f"{e['enonce']}{regles}",
              f"Priorité : {e['priorite']}. Vérification : {e['verification']}.", ""]
    p += ["## 8. Exigences non fonctionnelles", ""]
    for e in g["exigences_non_fonctionnelles"]:
        p += [f"### {e['id']} — {e['titre']}", "", e["enonce"], f"Preuve : {e['preuve']}.", ""]
    p += [
        "## 9. Contraintes", "",
        _table(["Id", "Contrainte"], [[c["id"], c["contrainte"]] for c in g["contraintes"]]), "",
        "## 10. API (résumé du delta)", "",
        _table(["Opération", "Delta", "Exigences"], operations_delta(g["openapi_delta"])), "",
        "## 11. Risques", "",
        _table(["Id", "Risque", "Mitigation"], [[r["id"], r["risque"], r["mitigation"]] for r in g["risques"]]), "",
        "## 12. Definition of Done de la fonctionnalité", "",
        "- Chaque EF et chaque ENF a au moins une preuve listée dans la matrice, et cette preuve passe.",
        "- Contrat validé et respecté par `/v3/api-docs`.",
        f"- Commits au format `feat({s}): … [EF-xx]` ; aucun fichier modifié hors du plan.",
        "- Diff relu et approuvé par un humain.", "",
        "## 13. Historique", "",
        _table(["Version", "Date", "Auteur", "Changement"], [
            ["0.1", decisions.get("date"), "neospec (modèle)", "Questions et hypothèses à partir du ticket seul"],
            ["0.2", decisions.get("date"), ", ".join(decideurs) or "—", "Hypothèses tranchées (porte 1)"],
            ["0.3", decisions.get("date"), "neospec (modèle)", f"Exigences, scénarios, contrat, plan, matrice ({statut})"],
        ]),
        "",
    ]
    return "\n".join(p)


def rendre_matrice(type_: str, g: dict[str, Any]) -> str:
    s = config.slug(type_)
    return "\n".join([
        f"# Matrice de traçabilité — {type_}", "",
        _table(["Champ", "Valeur"], [
            ["Spécification", f"`docs/specs/{type_}.md`"],
            ["Scénarios", f"`docs/specs/{s}/features/*.feature`"],
            ["Contrat", f"`docs/specs/{s}/openapi/{s}-delta.yaml`"],
            ["Vérification", f"`uv run --project labs/spec neospec valider --type {type_}`"],
        ]), "",
        "Statut : ⏳ preuve prévue · 🟢 preuve exécutée et verte · 🔴 preuve absente ou rouge.", "",
        _table(["Exigence", "Règles", "Scénario(s)", "Contrat (operationId)", "Tâche(s)", "Test(s) prévus", "Commit(s)", "Statut"],
               [[m["exigence"], m["regles"], m["scenarios"], m["contrat"], m["taches"], m["tests_prevus"], "—", "⏳"]
                for m in g["matrice"]]),
        "",
    ])


def rendre_plan(type_: str, g: dict[str, Any]) -> str:
    return "\n".join([
        f"# Plan technique — {type_}", "",
        "Nature : **D** déterministe (commande, script) · **A** agent (code vérifié par des tests) · **H** humain (décision, revue).", "",
        _table(["Id", "Nature", "Tâche", "Dépend de", "Exigences", "Fichiers attendus", "Vérification (fin de tâche)"],
               [[t["id"], t["nature"], t["tache"], ", ".join(t["depend_de"]) or "—", ", ".join(t["exigences"]) or "—",
                 t["fichiers"], t["verification"]] for t in g["plan"]]),
        "",
    ])


def prochain_numero_adr(dossier: Path, slug_adr: str) -> int:
    """Réutilise le numéro d'un ADR de même slug (réécriture idempotente), sinon prend le suivant."""
    numeros = []
    for f in dossier.glob("ADR-*.md") if dossier.exists() else []:
        m = re.match(r"ADR-(\d+)-(.+)\.md$", f.name)
        if m:
            if m.group(2) == slug_adr:
                return int(m.group(1))
            numeros.append(int(m.group(1)))
    return max(numeros, default=0) + 1


def rendre_adr(numero: int, type_: str, date: str, g: dict[str, Any]) -> str:
    a = g["adr"]
    return "\n".join([
        f"# ADR-{numero:03d} — {a['titre']}", "",
        _table(["Champ", "Valeur"], [
            ["Statut", "Proposé"], ["Date", date], ["Décideurs", "À désigner (tech lead, métier)"],
            ["Rédaction", "Assistant `neospec` (lab J03) ; à relire et amender par un humain"],
            ["Exigences concernées", ", ".join(a["exigences"]) or "—"],
            ["Spécification", f"`docs/specs/{type_}.md`"],
        ]), "",
        "Statut `Proposé` : seul un humain le passe à `Accepté`.", "",
        "## Contexte", "", a["contexte"], "",
        "## Options considérées", "",
        _table(["Option", "Description", "Avantages", "Inconvénients"],
               [[o["nom"], o["description"], o["avantages"], o["inconvenients"]] for o in a["options"]]), "",
        "## Recommandation", "", a["recommandation"], "",
        "## Conséquences négatives", "", a["consequences_negatives"], "",
        "## Indicateur de remise en cause", "", a["indicateur_remise_en_cause"], "",
    ])
