"""Lecture tolérante du journal de trajectoire de `neoagent` (contrat J4, labs/agent/README.md).

Une ligne JSON par événement :
  {"ts", "session", "etape", "type": "llm"|"tool_call"|"tool_result"|"approbation"|"erreur"|"fin",
   "outil", "entree", "sortie_extrait", "usage": {"input_tokens", "output_tokens",
   "cache_read_input_tokens"}, "modele"}

Le lecteur accepte des variantes raisonnables (horodatage ISO ou epoch, champ `statut` ou
`decision` en plus, `cache_creation_input_tokens` présent ou non, plusieurs sessions dans un
fichier, un dossier de journaux pour les workers d'un orchestrateur). Il ignore ce qu'il ne
connaît pas, compte les anomalies et les signale dans `avertissements` au lieu d'échouer.

Bibliothèque standard uniquement.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

CLES_USAGE = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")

# Outils de base du contrat (outils_de_base) et leur famille ; les autres sont « externes »
# (outil RAG du J5, outils MCP du J6, outils ajoutés par --outils-externes).
FAMILLES = {
    "lire_fichier": "lecture", "chercher": "lecture", "lister": "lecture", "git_diff": "lecture",
    "editer_fichier": "ecriture",
    "executer_commande": "execution",
}
OUTILS_ECRITURE = {"editer_fichier"}

CLASSES_COMMANDES = [
    ("tests", re.compile(r"(mvnw?|gradlew?)\b.*\b(test|verify)\b|npm (run )?test|npx (vitest|playwright)|"
                         r"\bvitest\b|\bplaywright test\b|\bpytest\b|make (test|e2e)")),
    ("scan", re.compile(r"\b(semgrep|gitleaks|trivy)\b")),
    ("build", re.compile(r"(mvnw?|gradlew?)\b.*\b(compile|package)\b|npm run build|\btsc\b")),
    ("git", re.compile(r"^\s*git\b")),
]
MOTIF_ECHEC = re.compile(r"BUILD FAILURE|Tests run:.*(Failures: [1-9]|Errors: [1-9])|\bFAIL(ED)?\b|"
                         r"\bERROR\b|code de sortie [1-9]|exit(ed)? (code )?[1-9]", re.I)
MOTIF_REFUS = re.compile(r"refus|rejet|deny|denied|non autoris|interdit|bloqu|hors (allowlist|périmètre)|"
                         r"not allowed|permission", re.I)
MOTIF_ACCEPTE = re.compile(r"^(ok|oui|yes|accept|approuv|valid|autoris|accord)", re.I)


def classe_commande(cmd: str) -> str:
    for nom, motif in CLASSES_COMMANDES:
        if motif.search(cmd or ""):
            return nom
    return "autre"


def famille(outil: str) -> str:
    return FAMILLES.get(outil, "externe")


def lire_ts(v: Any) -> dt.datetime | None:
    """ISO 8601 (avec ou sans fuseau, « Z » accepté) ou epoch en secondes ou millisecondes."""
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=dt.timezone.utc)
    if isinstance(v, str) and v:
        try:
            t = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
            return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return None
    return None


def normaliser_usage(u: Any) -> dict[str, int]:
    u = u if isinstance(u, dict) else {}
    return {k: int(u.get(k) or 0) for k in CLES_USAGE}


def somme_usages(usages: Iterable[dict[str, int]]) -> dict[str, int]:
    total = Counter()
    for u in usages:
        total.update(u)
    return {k: int(total.get(k, 0)) for k in CLES_USAGE}


def normaliser_fichiers(fichiers: Iterable[str], racine: str | None = None) -> set[str]:
    """Chemins relatifs au dépôt, sans doublon absolu/relatif."""
    rel = set()
    for f in fichiers:
        f = str(f).replace("\\", "/")
        if racine and f.startswith(racine.rstrip("/") + "/"):
            f = f[len(racine.rstrip("/")) + 1:]
        rel.add(f.removeprefix("./"))
    relatifs = {f for f in rel if not f.startswith("/")}
    return {f for f in rel if not (f.startswith("/") and any(f.endswith("/" + r) for r in relatifs))}


@dataclass
class AppelOutil:
    outil: str
    entree: Any
    sortie: str = ""
    etape: int | None = None
    debut: dt.datetime | None = None
    fin: dt.datetime | None = None
    statut: str = "inconnu"          # ok | erreur | refuse | inconnu (pas de tool_result)
    session: str = ""

    @property
    def famille(self) -> str:
        return famille(self.outil)

    @property
    def duree_s(self) -> float | None:
        if self.debut and self.fin:
            return max(0.0, (self.fin - self.debut).total_seconds())
        return None

    @property
    def commande(self) -> str:
        if self.outil != "executer_commande":
            return ""
        if isinstance(self.entree, dict):
            c = self.entree.get("commande") or self.entree.get("command") or self.entree.get("cmd") or ""
            return " ".join(c) if isinstance(c, list) else str(c)
        return str(self.entree)

    @property
    def chemin(self) -> str:
        if isinstance(self.entree, dict):
            for cle in ("chemin", "path", "fichier", "filePath", "file_path"):
                if self.entree.get(cle):
                    return str(self.entree[cle])
        return ""

    def texte_entree(self) -> str:
        return self.entree if isinstance(self.entree, str) else json.dumps(self.entree, ensure_ascii=False, sort_keys=True)


@dataclass
class Trajectoire:
    source: str
    sessions: list[str] = field(default_factory=list)
    appels: list[AppelOutil] = field(default_factory=list)
    appels_llm: list[dict] = field(default_factory=list)       # {etape, modele, usage, ts}
    approbations: list[dict] = field(default_factory=list)     # {etape, action, cible, accepte, ts}
    erreurs: list[str] = field(default_factory=list)
    fin: dict = field(default_factory=dict)                    # {statut, reponse}
    debut_ts: dt.datetime | None = None
    fin_ts: dt.datetime | None = None
    etape_max: int = 0
    usage_fin: dict = field(default_factory=dict)              # session → usage cumulé déclaré par « fin »
    avertissements: list[str] = field(default_factory=list)
    inconnus: Counter = field(default_factory=Counter)

    # ------------------------------------------------------------------ vues dérivées
    @property
    def duree_s(self) -> float | None:
        if self.debut_ts and self.fin_ts:
            return max(0.0, (self.fin_ts - self.debut_ts).total_seconds())
        return None

    @property
    def usage(self) -> dict[str, int]:
        return somme_usages(a["usage"] for a in self.appels_llm)

    def usage_par_modele(self) -> dict[str, dict[str, int]]:
        par: dict[str, list] = {}
        for a in self.appels_llm:
            par.setdefault(a["modele"] or "inconnu", []).append(a["usage"])
        return {m: somme_usages(us) for m, us in par.items()}

    @property
    def tokens_total(self) -> int:
        return sum(self.usage.values())

    @property
    def reponse(self) -> str:
        return str(self.fin.get("reponse") or "")

    @property
    def statut_fin(self) -> str:
        return str(self.fin.get("statut") or ("absent" if not self.fin else "inconnu"))

    def outils(self) -> Counter:
        return Counter(a.outil for a in self.appels)

    def familles(self) -> Counter:
        return Counter(a.famille for a in self.appels)

    def commandes(self) -> list[AppelOutil]:
        return [a for a in self.appels if a.outil == "executer_commande"]

    def executions_tests(self) -> list[AppelOutil]:
        return [a for a in self.commandes() if classe_commande(a.commande) == "tests"]

    def ecritures(self, statut: str | None = "ok") -> list[AppelOutil]:
        return [a for a in self.appels if a.outil in OUTILS_ECRITURE and (statut is None or a.statut == statut)]

    def refus(self) -> list[AppelOutil]:
        return [a for a in self.appels if a.statut == "refuse"]

    def fichiers_modifies(self, racine: str | None = None) -> set[str]:
        return normaliser_fichiers((a.chemin for a in self.ecritures() if a.chemin), racine)

    def resume(self) -> dict:
        durees = [d for d in (a.duree_s for a in self.appels) if d is not None]
        return {
            "source": self.source, "sessions": self.sessions, "statut_fin": self.statut_fin,
            "duree_s": round(self.duree_s, 1) if self.duree_s is not None else None,
            "etapes": self.etape_max, "appels_llm": len(self.appels_llm),
            "modeles": {m: sum(u.values()) for m, u in self.usage_par_modele().items()},
            "usage": self.usage, "tokens_total": self.tokens_total,
            "appels_outils": len(self.appels), "outils": dict(self.outils().most_common()),
            "familles": dict(self.familles().most_common()),
            "executions_tests": len(self.executions_tests()),
            "ecritures": len(self.ecritures()), "refus": len(self.refus()),
            "approbations": {"total": len(self.approbations),
                             "refusees": sum(1 for a in self.approbations if a["accepte"] is False)},
            "fichiers_modifies": sorted(self.fichiers_modifies()),
            "duree_outils_s": {"total": round(sum(durees), 1),
                               "mediane": round(statistics.median(durees), 2) if durees else None},
            "erreurs": self.erreurs, "avertissements": self.avertissements,
            "evenements_inconnus": dict(self.inconnus),
        }


class JournalIllisible(ValueError):
    pass


def _texte(v: Any) -> str:
    if v is None:
        return ""
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def _decision(ev: dict) -> bool | None:
    entree = ev.get("entree") if isinstance(ev.get("entree"), dict) else {}
    for cle in ("accordee", "accorde", "accepte", "approuve"):       # neoagent J4 : entree.accordee
        if isinstance(entree.get(cle), bool):
            return entree[cle]
    for cle in ("decision", "statut", "accepte", "approuve"):
        v = ev.get(cle)
        if isinstance(v, bool):
            return v
        if isinstance(v, str) and v:
            return bool(MOTIF_ACCEPTE.search(v)) and not MOTIF_REFUS.search(v)
    s = _texte(ev.get("sortie_extrait"))
    if MOTIF_REFUS.search(s):
        return False
    if MOTIF_ACCEPTE.search(s.strip()):
        return True
    return None


def _ajouter(t: Trajectoire, lignes: Iterable[tuple[str, int]]) -> None:
    en_attente: list[AppelOutil] = []
    for brute, num in lignes:
        brute = brute.strip()
        if not brute:
            continue
        try:
            ev = json.loads(brute)
        except json.JSONDecodeError:
            t.inconnus["ligne_non_json"] += 1
            continue
        if not isinstance(ev, dict):
            t.inconnus["ligne_non_objet"] += 1
            continue
        ts = lire_ts(ev.get("ts") or ev.get("timestamp"))
        if ts:
            t.debut_ts = ts if t.debut_ts is None else min(t.debut_ts, ts)
            t.fin_ts = ts if t.fin_ts is None else max(t.fin_ts, ts)
        session = str(ev.get("session") or "")
        if session and session not in t.sessions:
            t.sessions.append(session)
        etape = ev.get("etape") if isinstance(ev.get("etape"), int) else None
        if etape is not None:
            t.etape_max = max(t.etape_max, etape)
        typ = ev.get("type")
        if typ is None and isinstance(ev.get("usage"), dict) and ev.get("modele"):
            typ = "llm"            # journal d'usage sans « type » (assistant de spécification du J3 : une ligne par appel)
        outil = str(ev.get("outil") or "")
        if typ == "llm":
            t.appels_llm.append({"etape": etape, "modele": str(ev.get("modele") or ""),
                                 "usage": normaliser_usage(ev.get("usage")), "ts": ts})
        elif typ == "tool_call":
            a = AppelOutil(outil=outil or "inconnu", entree=ev.get("entree"), etape=etape, debut=ts, session=session)
            t.appels.append(a)
            en_attente.append(a)
        elif typ == "tool_result":
            a = next((x for x in en_attente if x.outil == outil and x.session == session), None) or \
                next((x for x in en_attente if x.outil == outil), None)
            if a is None:
                t.inconnus["tool_result_orphelin"] += 1
                continue
            en_attente.remove(a)
            a.sortie, a.fin = _texte(ev.get("sortie_extrait"))[:4000], ts
            statut = str(ev.get("statut") or "").lower()
            entree_r = ev.get("entree") if isinstance(ev.get("entree"), dict) else {}
            if statut in ("ok", "erreur", "refuse"):
                a.statut = statut
            elif MOTIF_REFUS.search(a.sortie[:200]):          # « REFUS GARDE-FOU », « REFUS HUMAIN » (J4)
                a.statut = "refuse"
            elif entree_r.get("is_error") is True or re.match(r"\s*(erreur|error|exception)", a.sortie, re.I):
                a.statut = "erreur"
            else:
                a.statut = "ok"
        elif typ == "approbation":
            entree = ev.get("entree") if isinstance(ev.get("entree"), dict) else {}
            appel = next((x for x in reversed(en_attente) if not outil or x.outil == outil), None)
            cible = entree.get("chemin") or entree.get("cible") or entree.get("commande") or (appel.chemin or appel.commande if appel else "")
            t.approbations.append({"etape": etape, "action": outil or entree.get("action") or entree.get("outil") or "",
                                   "cible": cible, "accepte": _decision(ev), "ts": ts})
        elif typ == "erreur":
            t.erreurs.append(_texte(ev.get("sortie_extrait") or ev.get("entree") or ev.get("message"))[:300])
        elif typ == "fin":
            entree = ev.get("entree") if isinstance(ev.get("entree"), dict) else {}
            statut = ev.get("statut") or entree.get("statut")
            t.fin = {"statut": statut or "termine", "reponse": _texte(ev.get("sortie_extrait"))}
            if isinstance(ev.get("usage"), dict):    # neoagent J4 : usage cumulé de la session dans « fin »
                t.usage_fin[session or "?"] = {"usage": normaliser_usage(ev["usage"]), "modele": str(ev.get("modele") or "")}
        else:
            t.inconnus[f"type:{typ}"] += 1
    if en_attente:
        t.avertissements.append(f"{len(en_attente)} appel(s) d'outil sans résultat (interruption, timeout ?)")


def lire_journal(chemin: str | Path) -> Trajectoire:
    """Lit un journal JSONL, ou tous les *.jsonl d'un dossier (workers d'un orchestrateur)."""
    chemin = Path(chemin)
    fichiers = sorted(chemin.glob("*.jsonl")) if chemin.is_dir() else [chemin]
    if not fichiers:
        raise JournalIllisible(f"{chemin} : aucun journal .jsonl")
    t = Trajectoire(source=str(chemin))
    for f in fichiers:
        lignes = f.read_text(encoding="utf-8", errors="replace").splitlines()
        _ajouter(t, ((l, i) for i, l in enumerate(lignes, 1)))
    if not t.appels_llm and not t.appels and not t.fin:
        raise JournalIllisible(f"{chemin} : aucun événement du contrat (llm, tool_call, fin…)")
    if t.usage_fin and not any(sum(a["usage"].values()) for a in t.appels_llm):
        # les événements llm ne portent pas l'usage : on se rabat sur l'usage cumulé de « fin » (une valeur par session)
        t.appels_llm = [a for a in t.appels_llm] + [{"etape": None, "modele": v["modele"], "usage": v["usage"], "ts": None}
                                                    for v in t.usage_fin.values()]
        t.avertissements.append("usage absent des événements llm : total repris de l'événement « fin » (pas de détail par appel)")
    if t.inconnus.get("ligne_non_json"):
        t.avertissements.append(f"{t.inconnus['ligne_non_json']} ligne(s) non JSON ignorée(s) (logs mêlés au journal ?)")
    if t.appels_llm and not any(a["modele"] for a in t.appels_llm):
        t.avertissements.append("champ « modele » absent des événements llm : coût par modèle impossible")
    if t.appels_llm and not any(a["usage"]["cache_creation_input_tokens"] for a in t.appels_llm) \
            and any(a["usage"]["cache_read_input_tokens"] for a in t.appels_llm):
        t.avertissements.append("cache_creation_input_tokens absent du journal (journal antérieur à l'ajout du champ "
                                "au contrat neoagent ?) : l'écriture du cache n'est pas comptée, coût sous-estimé")
    if not t.fin:
        t.avertissements.append("pas d'événement « fin » : session interrompue ?")
    return t
