"""Workflow LangGraph guidé d'assistance au développement sur NeoFlow (lab J09).

  START -> charger_contexte -> router_source -> rechercher -> verifier_preuves
        -> (relance : router_source) | (insuffisant : escalade) | proposer_action
        -> (action sensible : approbation [interrupt]) -> executer_action [idempotent] -> journal -> END

Garanties enseignées et testées (tests/) :
  - état sauvegardé après chaque super-step dans SQLite (SqliteSaver, durability="sync") ;
  - aucune action sensible sans approbation humaine (interrupt + revérification dans le nœud) ;
  - reprise après crash sans double exécution (clé d'idempotence + registre d'effets) ;
  - tentatives bornées (RetryPolicy), timeout par source, budget d'appels LLM et de tokens,
    recursion_limit comme filet de sécurité ;
  - rollback des effets par compensation (`annuler`), distinct du retour à un checkpoint (`rejouer`).

Exemples (mode offline, sans clé API) :
  python workflow.py lancer --offline --thread nf-402 --ticket NF-402 \
      --question "Où est calculé le niveau de validation d'une demande ?"
  python workflow.py approuver --offline --thread nf-402 --approbateur bob --crash-apres-effet
  python workflow.py reprendre --offline --thread nf-402
  python workflow.py journal --thread nf-402
"""
from __future__ import annotations

import argparse
import hashlib
import json
import operator
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RetryPolicy, interrupt

import extensions
import gitutil
import neoagent_pont
from config import charger, dossier_etat
from llm import SOURCES, ErreurTransitoire, RefusModele, creer_cerveau, ref_preuve
from memoire import MemoireRefusee, StoreMemoire
from sources import Sources, router_heuristique, source_suivante, verifier_preuves

ICI = Path(__file__).resolve().parent


def horodatage() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


# ====================================================================== état
class Etat(TypedDict, total=False):
    question: str
    ticket: str | None
    action_demandee: str | None
    portee: str
    demandeur: str
    commit_head: str
    memoires: list[dict]
    memoires_ecartees: list[dict]
    source: str
    requete: str
    sources_essayees: Annotated[list[str], operator.add]
    routage: Annotated[list[dict], operator.add]
    preuves: list[dict]
    preuves_obsoletes: Annotated[list[dict], operator.add]
    verification: dict
    relances: int
    proposition: dict | None
    approbation: dict | None
    resultat_action: dict | None
    consommation: dict
    degradations: Annotated[list[str], operator.add]
    statut: str
    motif_fin: str


# ====================================================================== journal
class Journal:
    """Journal d'exécution append-only (JSONL). Montre les rejeux : un nœud rejoué y apparaît deux fois."""

    def __init__(self, chemin: Path):
        self.chemin = chemin

    def evt(self, thread: str, noeud: str, message: str, **extra) -> None:
        ligne = {"ts": horodatage(), "thread": thread, "type": "evt", "noeud": noeud, "message": message, **extra}
        with self.chemin.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")

    def lire(self, thread: str | None = None) -> list[dict]:
        if not self.chemin.exists():
            return []
        lignes = [json.loads(l) for l in self.chemin.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [l for l in lignes if thread is None or l["thread"] == thread]

    def cloturer(self, thread: str, bilan: dict) -> bool:
        """Écrit le bilan une seule fois par thread (le nœud journal peut lui-même être rejoué)."""
        if any(l["type"] == "cloture" for l in self.lire(thread)):
            return False
        with self.chemin.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": horodatage(), "thread": thread, "type": "cloture", **bilan},
                               ensure_ascii=False) + "\n")
        return True


# ====================================================================== effets (registre idempotent)
def canonique(action: dict) -> str:
    return json.dumps({k: action.get(k) for k in ("type", "cible", "contenu")}, sort_keys=True, ensure_ascii=False)


def empreinte_action(action: dict) -> str:
    return hashlib.sha256(canonique(action).encode()).hexdigest()[:16]


class Effets:
    """Cible d'action simulée (commentaires de tickets) + registre des effets appliqués.

    La clé d'idempotence = hash(thread_id, action). L'effet et son enregistrement sont écrits
    dans la MÊME transaction : après un crash, soit les deux existent, soit aucun.
    Sur une API externe, on transmet la clé (en-tête Idempotency-Key) ou on passe par une outbox.
    """

    def __init__(self, chemin: Path):
        self.db = sqlite3.connect(str(chemin), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS commentaire_ticket (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ticket TEXT NOT NULL, auteur TEXT NOT NULL,
                contenu TEXT NOT NULL, cle_idempotence TEXT UNIQUE, cree_le TEXT NOT NULL,
                supprime INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS effet (
                cle TEXT PRIMARY KEY, thread_id TEXT NOT NULL, type TEXT NOT NULL, cible TEXT,
                resultat TEXT NOT NULL, compensation TEXT NOT NULL, cree_le TEXT NOT NULL, annule_le TEXT);
            CREATE TABLE IF NOT EXISTS intention (
                cle TEXT PRIMARY KEY, thread_id TEXT NOT NULL, type TEXT NOT NULL, statut TEXT NOT NULL,
                cree_le TEXT NOT NULL, maj_le TEXT NOT NULL);
        """)

    @staticmethod
    def cle(thread: str, action: dict) -> str:
        return hashlib.sha256(f"{thread}|{canonique(action)}".encode()).hexdigest()[:24]

    def deja_applique(self, cle: str) -> dict | None:
        r = self.db.execute("SELECT resultat FROM effet WHERE cle=?", (cle,)).fetchone()
        return json.loads(r["resultat"]) if r else None

    def appliquer(self, thread: str, action: dict, auteur: str, *, idempotent: bool = True) -> dict:
        """Référence : clé -> déjà appliqué ? -> sinon effet + registre dans une transaction."""
        if action["type"] != "commenter_ticket":
            raise ValueError(f"action non supportée : {action['type']}")
        cle = self.cle(thread, action)
        if idempotent and (existant := self.deja_applique(cle)):
            return {**existant, "rejoue": True}
        return self.appliquer_et_enregistrer(thread, action, auteur, cle if idempotent else None)

    def appliquer_et_enregistrer(self, thread: str, action: dict, auteur: str, cle: str | None) -> dict:
        """Primitive atomique : publie le commentaire ET, si `cle` est fournie, l'inscrit au registre,
        dans une seule transaction. `cle=None` : effet sans registre (contre-exemple)."""
        try:
            with self.db:  # transaction unique : effet + registre
                cur = self.db.execute(
                    "INSERT INTO commentaire_ticket (ticket, auteur, contenu, cle_idempotence, cree_le) "
                    "VALUES (?, ?, ?, ?, ?)", (action["cible"], auteur, action["contenu"], cle, horodatage()))
                resultat = {"statut": "applique", "type": action["type"], "ticket": action["cible"],
                            "commentaire_id": cur.lastrowid, "cle": cle}
                if cle:
                    self.db.execute(
                        "INSERT INTO effet (cle, thread_id, type, cible, resultat, compensation, cree_le) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (cle, thread, action["type"], action["cible"], json.dumps(resultat),
                         json.dumps({"type": "supprimer_commentaire", "commentaire_id": cur.lastrowid}),
                         horodatage()))
        except sqlite3.IntegrityError:  # deux reprises concurrentes : la contrainte UNIQUE tranche
            return {**(self.deja_applique(cle) or {"statut": "applique", "cle": cle}), "rejoue": True}
        return resultat

    def deleguer(self, thread: str, action: dict, executeur, cle: str) -> dict:
        """Effet EXTERNE non transactionnel (appel à neoagent) : journal d'intention + registre.

        On ne peut pas écrire l'appel et sa trace dans une même transaction. On inscrit donc l'intention
        AVANT l'appel ; si une reprise trouve une intention « en_cours » sans résultat, l'appel a peut-être eu
        lieu : on le relance (acceptable ici car l'agent est en lecture seule) et on le signale.
        """
        if existant := self.deja_applique(cle):
            return {**existant, "rejoue": True}
        intention = self.db.execute("SELECT statut FROM intention WHERE cle=?", (cle,)).fetchone()
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO intention (cle, thread_id, type, statut, cree_le, maj_le) "
                            "VALUES (?, ?, ?, 'en_cours', ?, ?)", (cle, thread, action["type"], horodatage(), horodatage()))
        try:
            sortie = dict(executeur())
        except Exception:
            with self.db:     # l'appel a échoué : l'intention n'est pas « en cours » pour toujours
                self.db.execute("UPDATE intention SET statut='echec', maj_le=? WHERE cle=?", (horodatage(), cle))
            raise
        resultat = {**{k: v for k, v in sortie.items() if k != "statut"}, "statut_agent": sortie.get("statut"),
                    "statut": "applique", "type": action["type"], "cible": action.get("cible"), "cle": cle,
                    "relance_apres_interruption": intention is not None}
        with self.db:
            self.db.execute("UPDATE intention SET statut='fait', maj_le=? WHERE cle=?", (horodatage(), cle))
            self.db.execute("INSERT INTO effet (cle, thread_id, type, cible, resultat, compensation, cree_le) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (cle, thread, action["type"], action.get("cible"), json.dumps(resultat, default=str),
                             json.dumps({"type": "aucune", "raison": "délégation en lecture seule"}), horodatage()))
        return resultat

    def compenser(self, thread: str) -> list[dict]:
        """Rollback métier : applique les compensations enregistrées (idempotent)."""
        faits = []
        for r in self.db.execute("SELECT * FROM effet WHERE thread_id=? AND annule_le IS NULL", (thread,)).fetchall():
            comp = json.loads(r["compensation"])
            if comp.get("type") != "supprimer_commentaire":
                continue  # rien à compenser (lecture seule)
            with self.db:
                self.db.execute("UPDATE commentaire_ticket SET supprime=1 WHERE id=?", (comp["commentaire_id"],))
                self.db.execute("UPDATE effet SET annule_le=? WHERE cle=?", (horodatage(), r["cle"]))
            faits.append({"cle": r["cle"], **comp})
        return faits

    def commentaires(self, ticket: str, inclure_supprimes: bool = False) -> list[dict]:
        sql = "SELECT * FROM commentaire_ticket WHERE ticket=?" + ("" if inclure_supprimes else " AND supprime=0")
        return [dict(r) for r in self.db.execute(sql + " ORDER BY id", (ticket,))]


# ====================================================================== contexte d'exécution
@dataclass
class Contexte:
    """Dépendances non sérialisables, injectées par fermeture (elles ne vont pas dans le checkpoint)."""
    cfg: dict
    depot: Path
    etat_dir: Path
    cerveau: Any
    sources: Sources
    memoire: StoreMemoire
    effets: Effets
    journal: Journal
    idempotence: bool = True
    crash_apres_effet: bool = False
    offline: bool = True
    routeur: Any = router_heuristique          # TP2 : extensions.routeur
    suite: Any = source_suivante               # TP2 : extensions.source_suivante
    options: dict = field(default_factory=dict)


def budget_ok(conso: dict, cfg: dict, besoin: int = 1) -> bool:
    b = cfg["budget"]
    return conso.get("appels_llm", 0) + besoin <= b["appels_llm"] and conso.get("tokens", 0) < b["tokens"]


def cumuler(conso: dict, usage: dict) -> dict:
    return {"appels_llm": conso.get("appels_llm", 0) + usage.get("appels", 0),
            "tokens": conso.get("tokens", 0) + usage.get("tokens", 0)}


def _thread(config: RunnableConfig) -> str:
    return config["configurable"]["thread_id"]


# ====================================================================== graphe
def construire_graphe(ctx: Contexte, checkpointer):
    cfg = ctx.cfg

    def charger_contexte(etat: Etat, config: RunnableConfig) -> dict:
        valides, ecartees = ctx.memoire.rechercher(etat["question"], [etat["portee"]], depot=ctx.depot)
        ctx.journal.evt(_thread(config), "charger_contexte",
                        f"{len(valides)} souvenir(s) valide(s), {len(ecartees)} écarté(s)")
        return {
            "commit_head": gitutil.head(ctx.depot),
            "memoires": [{"id": m.id, "type": m.type, "contenu": m.contenu, "provenance": m.provenance}
                         for m in valides],
            "memoires_ecartees": [{"id": m.id, "provenance": m.provenance, "motif": motif} for m, motif in ecartees],
            "relances": 0, "consommation": {"appels_llm": 0, "tokens": 0}, "statut": "en_cours",
        }

    def router_source(etat: Etat, config: RunnableConfig) -> dict:
        essayees, conso, q = etat.get("sources_essayees", []), etat["consommation"], etat["question"]
        relances = etat.get("relances", 0)
        if not essayees:
            source, motif = ctx.routeur(q)
            requete, mode = q, "règle"
            if source is None:
                if budget_ok(conso, cfg):
                    d, usage = ctx.cerveau.choisir_source(q, list(SOURCES))
                    source, requete, motif, mode = d["source"], d["requete"], d["justification"], "llm"
                    conso = cumuler(conso, usage)
                else:
                    source, motif, mode = "hybride", "budget LLM épuisé : source par défaut", "défaut"
        else:
            source = ctx.suite(essayees[-1], essayees)
            motif, mode, requete, relances = (f"preuves insuffisantes via {essayees[-1]} : bascule",
                                              "relance", q, relances + 1)
            if budget_ok(conso, cfg):
                requete, usage = ctx.cerveau.reformuler(q, source, etat.get("preuves", []))
                conso = cumuler(conso, usage)
        ctx.journal.evt(_thread(config), "router_source", f"{source} ({mode}) : {motif}")
        return {"source": source, "requete": requete, "sources_essayees": [source], "relances": relances,
                "routage": [{"source": source, "mode": mode, "motif": motif, "requete": requete}],
                "consommation": conso}

    def rechercher(etat: Etat, config: RunnableConfig) -> dict:
        try:
            res = ctx.sources.rechercher(etat["source"], etat["requete"], cfg["preuves"]["k"])
        except ErreurTransitoire as exc:
            ctx.journal.evt(_thread(config), "rechercher", f"échec transitoire : {exc}", tentative=ctx.sources.appels)
            raise  # la RetryPolicy décide de retenter ; au-delà, le run échoue et le checkpoint reste
        nouvelles = [d for d in ctx.sources.degradations if d not in etat.get("degradations", [])]
        ctx.journal.evt(_thread(config), "rechercher", f"{len(res)} résultat(s) via {etat['source']}",
                        tentative=ctx.sources.appels)
        return {"preuves": res, "degradations": nouvelles}

    def verifier(etat: Etat, config: RunnableConfig) -> dict:
        v = verifier_preuves(etat["question"], etat.get("preuves", []), ctx.depot, etat["source"], cfg,
                             idf=ctx.sources.idf)
        ctx.journal.evt(_thread(config), "verifier_preuves",
                        f"{v['motif']} ; {len(v['obsoletes'])} preuve(s) obsolète(s) écartée(s)")
        return {"preuves": v["fraiches"], "preuves_obsoletes": v["obsoletes"],
                "verification": {k: v[k] for k in ("suffisant", "motif", "couverture", "nb_fraiches", "head")}}

    def apres_verification(etat: Etat) -> str:
        if etat["verification"]["suffisant"]:
            return "proposer_action"
        suivante = ctx.suite(etat["source"], etat.get("sources_essayees", []))
        if suivante and etat.get("relances", 0) < cfg["limites"]["max_relances"]:
            return "router_source"
        return "escalade"

    def escalade(etat: Etat, config: RunnableConfig) -> dict:
        motif = etat.get("motif_fin") or (f"preuves insuffisantes après {len(etat.get('sources_essayees', []))} "
                                          f"source(s) : {etat.get('verification', {}).get('motif')}")
        ctx.journal.evt(_thread(config), "escalade", motif)
        return {"statut": "escalade", "motif_fin": motif}

    def proposer_action(etat: Etat, config: RunnableConfig) -> dict:
        if not budget_ok(etat["consommation"], cfg):
            return {"proposition": None, "motif_fin": "budget LLM épuisé avant la rédaction"}
        try:
            prop, usage = ctx.cerveau.proposer(etat["question"], etat["preuves"], etat.get("memoires", []),
                                               etat.get("ticket"))
        except RefusModele as exc:
            return {"proposition": None, "motif_fin": f"refus du modèle : {exc}"}
        if etat.get("action_demandee") == "deleguer_neoagent":
            prop["action"] = {"type": "deleguer_neoagent", "cible": "neoagent", "contenu": (
                f"Analyse en LECTURE SEULE du dépôt NeoFlow pour répondre à : {etat['question']}\n"
                f"Points de départ (preuves vérifiées) : {', '.join(prop.get('citations', [])[:5])}\n"
                "Rends un rapport de 10 lignes maximum, chaque affirmation citée chemin:lignes. "
                "Ne modifie aucun fichier.")}
        refs = {ref_preuve(p) for p in etat["preuves"]}
        prop["citations_invalides"] = [c for c in prop.get("citations", []) if c not in refs]
        prop["sensible"] = prop["action"]["type"] in cfg["actions_sensibles"]
        ctx.journal.evt(_thread(config), "proposer_action",
                        f"action {prop['action']['type']} ; {len(prop['citations'])} citation(s), "
                        f"{len(prop['citations_invalides'])} invalide(s)")
        return {"proposition": prop, "consommation": cumuler(etat["consommation"], usage)}

    def apres_proposition(etat: Etat) -> str:
        prop = etat.get("proposition")
        if prop is None:
            return "escalade"
        return "approbation" if prop["sensible"] else "journal"

    def approbation(etat: Etat, config: RunnableConfig) -> dict:
        # ATTENTION : à la reprise, LangGraph ré-exécute ce nœud depuis le début.
        # Rien avant interrupt() ne doit avoir d'effet de bord.
        prop = etat["proposition"]
        reponse = interrupt({
            "type": "approbation_requise", "action": prop["action"], "citations": prop["citations"],
            "citations_invalides": prop["citations_invalides"],
            "preuves_obsoletes_ecartees": len(etat.get("preuves_obsoletes", [])),
            "consigne": "Répondre {decision: approuver|refuser|modifier, approbateur, contenu?}",
        })
        decision, motif = _valider_reponse(reponse, etat.get("demandeur"))
        action = prop["action"]
        if decision == "modifier":
            action = {**action, "contenu": reponse["contenu"]}
            decision = "approuver"
        approbateur = reponse.get("approbateur") if isinstance(reponse, dict) else None
        appro = {"decision": decision, "motif": motif, "approbateur": approbateur,
                 "modifiee": action != prop["action"], "horodatage": horodatage(),
                 "empreinte": empreinte_action(action)}
        ctx.journal.evt(_thread(config), "approbation", f"{decision} par {appro['approbateur']} ({motif})")
        return {"approbation": appro, "proposition": {**prop, "action": action}}

    def apres_approbation(etat: Etat) -> str:
        return "executer_action" if etat["approbation"]["decision"] == "approuver" else "journal"

    def executer_action(etat: Etat, config: RunnableConfig) -> dict:
        thread = _thread(config)
        ctx.journal.evt(thread, "executer_action", "début du nœud")
        prop, appro = etat.get("proposition") or {}, etat.get("approbation") or {}
        # Défense en profondeur : le câblage du graphe ne suffit pas, on revérifie ici.
        if appro.get("decision") != "approuver":
            return _bloquer(thread, "aucune approbation valide")
        if appro.get("empreinte") != empreinte_action(prop.get("action", {})):
            return _bloquer(thread, "action modifiée après approbation")
        action = prop["action"]
        if action["type"] == "deleguer_neoagent":
            try:
                res = ctx.effets.deleguer(thread, action, lambda: neoagent_pont.deleguer(
                    action["contenu"], ctx.depot, cfg, offline=ctx.offline,
                    journal=ctx.etat_dir / f"neoagent-{thread}.jsonl"), Effets.cle(thread, action))
            except neoagent_pont.NeoagentIndisponible as exc:
                ctx.journal.evt(thread, "executer_action", f"neoagent indisponible : {exc}")
                return {"resultat_action": {"statut": "indisponible", "motif": str(exc)}, "statut": "escalade",
                        "motif_fin": f"délégation impossible : {exc}"}
            message = ("délégation déjà faite (clé connue) : ignorée" if res.get("rejoue") else
                       f"neoagent exécuté ({res.get('statut_agent')}, outils : {', '.join(res.get('outils', []))})")
        else:
            res = ctx.effets.appliquer(thread, action, auteur=f"assistant (approuvé par {appro['approbateur']})",
                                       idempotent=ctx.idempotence)
            message = ("effet déjà appliqué (clé connue) : ignoré" if res.get("rejoue")
                       else f"effet appliqué : commentaire {res['commentaire_id']} sur {res['ticket']}")
        ctx.journal.evt(thread, "executer_action", message, cle=res.get("cle"))
        if ctx.crash_apres_effet and not res.get("rejoue"):
            print(f"!! crash simulé APRÈS l'effet et AVANT le checkpoint du nœud (thread {thread})", flush=True)
            os._exit(137)
        return {"resultat_action": res, "statut": "termine"}

    def _bloquer(thread: str, motif: str) -> dict:
        ctx.journal.evt(thread, "executer_action", f"BLOQUÉ : {motif}")
        return {"resultat_action": {"statut": "bloque", "motif": motif}, "statut": "bloque", "motif_fin": motif}

    def journal(etat: Etat, config: RunnableConfig) -> dict:
        thread = _thread(config)
        statut = etat.get("statut", "en_cours")
        if (etat.get("approbation") or {}).get("decision") == "refuser":
            statut = "refuse"
        elif statut == "en_cours":
            statut = "termine"
        bilan = {
            "statut": statut, "motif_fin": etat.get("motif_fin"), "question": etat["question"],
            "commit": etat.get("commit_head"), "sources": etat.get("sources_essayees", []),
            "preuves": [ref_preuve(p) for p in etat.get("preuves", [])],
            "preuves_obsoletes": [p["motif"] for p in etat.get("preuves_obsoletes", [])],
            "memoires_utilisees": [m["provenance"] for m in etat.get("memoires", [])],
            "memoires_ecartees": etat.get("memoires_ecartees", []),
            "action": (etat.get("proposition") or {}).get("action"), "approbation": etat.get("approbation"),
            "resultat_action": etat.get("resultat_action"), "consommation": etat.get("consommation"),
            "degradations": etat.get("degradations", []), "cerveau": ctx.cerveau.nom,
        }
        ctx.journal.cloturer(thread, bilan)
        if statut == "termine" and etat.get("preuves"):
            _memoriser_episode(etat, thread)
        return {"statut": statut}

    def _memoriser_episode(etat: Etat, thread: str) -> None:
        p = next((p for p in etat["preuves"] if p.get("source_type") != "git"), etat["preuves"][0])
        lignes = f":{p['start_line']}-{p['end_line']}" if p.get("start_line") else ""
        try:
            action = (etat.get("resultat_action") or {})
            issue = ("réponse sans action" if action.get("statut") != "applique" else
                     f"commentaire publié sur {action['ticket']} après approbation" if action.get("ticket") else
                     f"{action.get('type')} exécutée après approbation")
            ctx.memoire.ajouter("episodique", f"{horodatage()[:10]} : question « {etat['question']} » "
                                f"(thread {thread}) traitée via {', '.join(etat.get('sources_essayees', []))} ; "
                                f"{issue} ; preuve principale {p['path']}", etat["portee"],
                                source=f"{p['path']}@{p['commit']}{lignes}", depot=ctx.depot, auteur="agent:workflow")
        except (MemoireRefusee, gitutil.ErreurGit) as exc:
            ctx.journal.evt(thread, "journal", f"épisode non mémorisé : {exc}")

    politique = RetryPolicy(max_attempts=cfg["retries"]["max_tentatives"],
                            initial_interval=cfg["retries"]["intervalle_initial_s"],
                            backoff_factor=cfg["retries"]["facteur"], jitter=cfg["retries"]["jitter"],
                            retry_on=ErreurTransitoire)

    # TP3 : un module d'extension peut remplacer approbation, executer_action et apres_verification.
    ext = extensions.module(cfg, "noeuds")
    if ext is not None and hasattr(ext, "approbation"):
        def approbation(etat: Etat, config: RunnableConfig) -> dict:  # noqa: F811
            return ext.approbation(etat, config, ctx)
    if ext is not None and hasattr(ext, "executer_action"):
        def executer_action(etat: Etat, config: RunnableConfig) -> dict:  # noqa: F811
            res = ext.executer_action(etat, config, ctx)
            ra = (res or {}).get("resultat_action") or {}
            if ctx.crash_apres_effet and ra.get("statut") == "applique" and not ra.get("rejoue"):
                print(f"!! crash simulé APRÈS l'effet et AVANT le checkpoint du nœud ({_thread(config)})", flush=True)
                os._exit(137)
            return res
    if ext is not None and hasattr(ext, "apres_verification"):
        def apres_verification(etat: Etat) -> str:  # noqa: F811
            return ext.apres_verification(etat, ctx)

    g = StateGraph(Etat)
    g.add_node("charger_contexte", charger_contexte)
    g.add_node("router_source", router_source)
    g.add_node("rechercher", rechercher, retry_policy=politique)
    g.add_node("verifier_preuves", verifier)
    g.add_node("proposer_action", proposer_action, retry_policy=politique)
    g.add_node("approbation", approbation)
    g.add_node("executer_action", executer_action)
    g.add_node("escalade", escalade)
    g.add_node("journal", journal)
    g.add_edge(START, "charger_contexte")
    g.add_edge("charger_contexte", "router_source")
    g.add_edge("router_source", "rechercher")
    g.add_edge("rechercher", "verifier_preuves")
    g.add_conditional_edges("verifier_preuves", apres_verification,
                            ["proposer_action", "router_source", "escalade"])
    g.add_conditional_edges("proposer_action", apres_proposition, ["approbation", "journal", "escalade"])
    g.add_conditional_edges("approbation", apres_approbation, ["executer_action", "journal"])
    g.add_edge("executer_action", "journal")
    g.add_edge("escalade", "journal")
    g.add_edge("journal", END)
    return g.compile(checkpointer=checkpointer)


def _valider_reponse(reponse: Any, demandeur: str | None) -> tuple[str, str]:
    """Fail closed : toute réponse mal formée vaut refus."""
    if not isinstance(reponse, dict):
        return "refuser", "réponse d'approbation illisible"
    decision, approbateur = reponse.get("decision"), (reponse.get("approbateur") or "").strip()
    if decision not in ("approuver", "refuser", "modifier"):
        return "refuser", f"décision inconnue {decision!r}"
    if not approbateur or approbateur.startswith("agent"):
        return "refuser", "approbateur humain obligatoire"
    if decision != "refuser" and demandeur and approbateur == demandeur:
        return "refuser", "le demandeur ne peut pas s'auto-approuver (principe des quatre yeux)"
    if decision == "modifier" and not (reponse.get("contenu") or "").strip():
        return "refuser", "modification sans contenu"
    return decision, "décision humaine valide"


# ====================================================================== exécution
@dataclass
class Session:
    ctx: Contexte
    graphe: Any
    conn: sqlite3.Connection

    def config(self, thread: str, checkpoint_id: str | None = None) -> dict:
        c: dict = {"configurable": {"thread_id": thread}, "recursion_limit": self.ctx.cfg["limites"]["recursion_limit"]}
        if checkpoint_id:
            c["configurable"]["checkpoint_id"] = checkpoint_id
        return c

    def invoquer(self, entree, thread: str, checkpoint_id: str | None = None):
        # durability="sync" : le checkpoint est écrit AVANT de passer au super-step suivant.
        return self.graphe.invoke(entree, self.config(thread, checkpoint_id), durability="sync")

    def instantane(self, thread: str):
        return self.graphe.get_state(self.config(thread))

    def en_attente(self, thread: str) -> dict | None:
        snap = self.instantane(thread)
        for t in snap.tasks:
            if t.interrupts:
                return t.interrupts[0].value
        return None

    def fermer(self):
        self.ctx.sources.fermer()
        self.conn.close()


def ouvrir_session(*, offline: bool, etat: str | None = None, depot: str | None = None, config: str | None = None,
                   panne: int = 0, lenteur_s: float = 0.0, idempotence: bool = True,
                   crash_apres_effet: bool = False, cfg: dict | None = None) -> Session:
    cfg = cfg or charger(config)
    etat_dir = dossier_etat(etat)
    depot_p = gitutil.racine_depot(depot or ICI)
    ctx = Contexte(cfg=cfg, depot=depot_p, etat_dir=etat_dir, cerveau=creer_cerveau(cfg, offline),
                   sources=Sources(depot_p, cfg, panne=panne, lenteur_s=lenteur_s),
                   memoire=StoreMemoire(etat_dir / "memoire.db", cfg), effets=Effets(etat_dir / "effets.db"),
                   journal=Journal(etat_dir / "journal.jsonl"), idempotence=idempotence,
                   crash_apres_effet=crash_apres_effet, offline=offline,
                   routeur=extensions.fonction(cfg, "routeur", router_heuristique),
                   suite=extensions.fonction(cfg, "source_suivante", source_suivante))
    conn = sqlite3.connect(str(etat_dir / "checkpoints.db"), check_same_thread=False)
    return Session(ctx, construire_graphe(ctx, SqliteSaver(conn)), conn)


def afficher(s: Session, thread: str) -> None:
    snap = s.instantane(thread)
    v = snap.values
    print(f"thread={thread} statut={v.get('statut')} prochain={list(snap.next) or '-'} "
          f"sources={v.get('sources_essayees')} conso={v.get('consommation')}")
    if v.get("degradations"):
        print("  dégradations :", "; ".join(v["degradations"]))
    if v.get("memoires_ecartees"):
        print("  mémoires écartées :", "; ".join(f"{m['provenance']} ({m['motif']})" for m in v["memoires_ecartees"]))
    if v.get("preuves_obsoletes"):
        print("  preuves obsolètes écartées :", "; ".join(p["motif"] for p in v["preuves_obsoletes"]))
    attente = s.en_attente(thread)
    if attente:
        a = attente["action"]
        print(f"  EN ATTENTE D'APPROBATION : {a['type']} -> {a['cible']}")
        print("  " + (a.get("contenu") or "").replace("\n", "\n  "))
        print(f"  citations invalides : {attente['citations_invalides'] or 'aucune'}")
        print(f"  -> python workflow.py approuver --thread {thread} --approbateur <login> "
              f"[--decision refuser|modifier --contenu ...]")
    elif v.get("resultat_action"):
        print(f"  résultat : {v['resultat_action']}")
    if v.get("motif_fin"):
        print(f"  motif : {v['motif_fin']}")


def main(argv: list[str] | None = None) -> int:
    commun = argparse.ArgumentParser(add_help=False)
    commun.add_argument("--offline", action="store_true", default=os.environ.get("NEOFLOW_OFFLINE") == "1",
                        help="LLM simulé déterministe (aucun appel réseau, aucune clé)")
    commun.add_argument("--etat", help="dossier d'état (défaut : labs/workflow/.etat ou $NEOFLOW_ETAT)")
    commun.add_argument("--depot", help="dépôt Git analysé (défaut : dépôt contenant le lab)")
    commun.add_argument("--config", help="fichier YAML surchargeant config.yaml")
    exec_opts = argparse.ArgumentParser(add_help=False)
    exec_opts.add_argument("--panne-retriever", type=int, default=0, help="nb d'appels de recherche en échec")
    exec_opts.add_argument("--lenteur-s", type=float, default=0.0, help="latence injectée dans les sources")
    exec_opts.add_argument("--crash-apres-effet", action="store_true", help="tue le processus juste après l'effet")
    exec_opts.add_argument("--sans-idempotence", action="store_true", help="désactive la clé (démo du problème)")

    p = argparse.ArgumentParser(description="Workflow LangGraph NeoFlow (lab J09)")
    sp = p.add_subparsers(dest="cmd", required=True)
    lan = sp.add_parser("lancer", parents=[commun, exec_opts])
    lan.add_argument("--thread", required=True)
    lan.add_argument("--question", required=True)
    lan.add_argument("--ticket")
    lan.add_argument("--action", default="auto", choices=["auto", "commenter_ticket", "deleguer_neoagent"],
                     help="auto : commentaire si --ticket, sinon réponse seule ; deleguer_neoagent : agent du J4")
    lan.add_argument("--portee")
    lan.add_argument("--demandeur", default=os.environ.get("USER", "alice"))
    ap = sp.add_parser("approuver", parents=[commun, exec_opts])
    ap.add_argument("--thread", required=True)
    ap.add_argument("--decision", default="approuver", choices=["approuver", "refuser", "modifier"])
    ap.add_argument("--approbateur", required=True)
    ap.add_argument("--contenu")
    rep = sp.add_parser("reprendre", parents=[commun, exec_opts])
    rep.add_argument("--thread", required=True)
    rej = sp.add_parser("rejouer", parents=[commun, exec_opts], help="fork depuis un checkpoint passé")
    rej.add_argument("--thread", required=True)
    rej.add_argument("--checkpoint", required=True)
    for nom in ("etat", "historique", "annuler"):
        sp.add_parser(nom, parents=[commun]).add_argument("--thread", required=True)
    jr = sp.add_parser("journal", parents=[commun])
    jr.add_argument("--thread")
    cm = sp.add_parser("commentaires", parents=[commun])
    cm.add_argument("--ticket", required=True)
    sp.add_parser("graphe", parents=[commun])
    a = p.parse_args(argv)

    s = ouvrir_session(offline=a.offline or a.cmd not in ("lancer", "approuver", "reprendre", "rejouer"),
                       etat=a.etat, depot=a.depot, config=a.config,
                       panne=getattr(a, "panne_retriever", 0), lenteur_s=getattr(a, "lenteur_s", 0.0),
                       idempotence=not getattr(a, "sans_idempotence", False),
                       crash_apres_effet=getattr(a, "crash_apres_effet", False))
    try:
        return _executer(a, s)
    except ErreurTransitoire as exc:
        print(f"ÉCHEC après {s.ctx.cfg['retries']['max_tentatives']} tentative(s) : {exc}")
        print(f"  checkpoint conservé, prochain nœud : {list(s.instantane(a.thread).next)} "
              f"-> corriger puis : python workflow.py reprendre --thread {a.thread}")
        return 1
    except GraphRecursionError as exc:
        print(f"ARRÊT : recursion_limit={s.ctx.cfg['limites']['recursion_limit']} atteinte ({exc})")
        return 1
    finally:
        s.fermer()


def _executer(a, s: Session) -> int:
    if a.cmd == "lancer":
        if s.instantane(a.thread).values:
            print(f"le thread {a.thread} existe déjà : utilisez `reprendre`, `etat` ou un autre --thread")
            return 2
        s.invoquer({"question": a.question, "ticket": a.ticket, "demandeur": a.demandeur,
                    "action_demandee": None if a.action == "auto" else a.action,
                    "portee": a.portee or s.ctx.cfg["portee_defaut"]}, a.thread)
        afficher(s, a.thread)
    elif a.cmd == "approuver":
        if not s.en_attente(a.thread):
            print(f"aucune approbation en attente sur {a.thread}")
            return 2
        s.invoquer(Command(resume={"decision": a.decision, "approbateur": a.approbateur, "contenu": a.contenu}),
                   a.thread)
        afficher(s, a.thread)
    elif a.cmd == "reprendre":
        snap = s.instantane(a.thread)
        if s.en_attente(a.thread):
            print("en attente d'approbation humaine : utilisez `approuver` (la reprise ne vaut pas accord)")
            return 2
        if not snap.next:
            print(f"rien à reprendre (statut {snap.values.get('statut')})")
            return 0
        print(f"reprise depuis le checkpoint {snap.config['configurable']['checkpoint_id']} -> {list(snap.next)}")
        s.invoquer(None, a.thread)
        afficher(s, a.thread)
    elif a.cmd == "rejouer":
        s.invoquer(None, a.thread, a.checkpoint)
        afficher(s, a.thread)
    elif a.cmd == "etat":
        afficher(s, a.thread)
    elif a.cmd == "historique":
        for snap in s.graphe.get_state_history(s.config(a.thread)):
            md = snap.metadata or {}
            print(f"{snap.config['configurable']['checkpoint_id']}  step={md.get('step'):>3}  "
                  f"source={md.get('source', '?'):<6} prochain={list(snap.next) or '-'}  "
                  f"statut={snap.values.get('statut')}")
    elif a.cmd == "journal":
        for l in s.ctx.journal.lire(a.thread):
            if l["type"] == "cloture":
                print(f"{l['ts']} [{l['thread']}] CLÔTURE statut={l['statut']} action={l.get('resultat_action')}")
            else:
                extra = f" (tentative {l['tentative']})" if l.get("tentative") else ""
                print(f"{l['ts']} [{l['thread']}] {l['noeud']:<17} {l['message']}{extra}")
    elif a.cmd == "annuler":
        faits = s.ctx.effets.compenser(a.thread)
        for f in faits:
            s.ctx.journal.evt(a.thread, "annuler", f"compensation {f['type']} #{f['commentaire_id']}")
        print(f"{len(faits)} compensation(s) appliquée(s)" if faits else "aucun effet à compenser")
    elif a.cmd == "commentaires":
        for c in s.ctx.effets.commentaires(a.ticket, inclure_supprimes=True):
            etat = "SUPPRIMÉ" if c["supprime"] else "visible"
            print(f"#{c['id']} {c['ticket']} [{etat}] {c['auteur']} cle={c['cle_idempotence']}")
    elif a.cmd == "graphe":
        print(s.graphe.get_graph().draw_mermaid())
    return 0


if __name__ == "__main__":
    sys.exit(main())
