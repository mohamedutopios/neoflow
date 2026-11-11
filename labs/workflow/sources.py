"""Agentic RAG : routage entre sources, récupération avec timeout, vérification des preuves.

Sources disponibles (toutes renvoient des « preuves » au format du lab RAG J05 :
path, start_line, end_line, symbol, commit, score, text, source_type, + source) :
  symboles   définition et usages d'un identifiant (git grep, déterministe)
  lexical    chaîne exacte, message d'erreur, clé de config (BM25 du lab RAG, sinon BM25 local)
  vectoriel  question conceptuelle (lab RAG, mode vectoriel)
  hybride    fusion RRF lexical + vectoriel (lab RAG)
  documents  ADR, specs, tickets, README (Markdown uniquement)
  git        historique : qui, quand, pourquoi (git log -S / --grep)

Le lab RAG (labs/rag/search.py, API `Searcher(config_path=None).search(query, mode, k)`) est
importé de façon tolérante. S'il est absent ou injoignable, on DÉGRADE vers une recherche
lexicale locale et on le trace : le workflow reste utilisable et le journal dit pourquoi.

Trois familles d'erreurs, trois traitements :
  ErreurTransitoire  (timeout, 429/5xx, panne simulée)  -> RetryPolicy du graphe, bornée
  SourceIndisponible (lab absent, Qdrant éteint)        -> dégradation tracée, sans retry
  autres exceptions  (bug, entrée invalide)             -> propagées, le run échoue, checkpoint conservé
"""
from __future__ import annotations

import concurrent.futures as cf
import math
import re
import sys
import unicodedata
from collections import Counter
from fnmatch import fnmatch
from pathlib import Path

import gitutil
from llm import SOURCES, ErreurTransitoire

ICI = Path(__file__).resolve().parent

# Chaîne de repli quand les preuves sont insuffisantes (agentic RAG : on change de source).
SUITE = {
    "symboles": ["lexical", "hybride", "git"],
    "lexical": ["hybride", "symboles", "vectoriel"],
    "vectoriel": ["hybride", "lexical", "documents"],
    "hybride": ["lexical", "symboles", "documents"],
    "documents": ["hybride", "lexical", "git"],
    "git": ["symboles", "hybride", "documents"],
}

REGLES_ROUTAGE = [
    # « quand » seul est ambigu (« quand le montant est nul » = condition) : on exige un verbe de changement.
    ("git", re.compile(r"(depuis quand|^\s*quand\b|quand .*\b(chang|modifi|introdu|ajout|supprim|cass)|"
                       r"\bqui a (introduit|modifi|chang|ajout|supprim|cass|[ée]crit)|\bhistorique\b|\bcommit\b|"
                       r"\br[ée]gression\b|modifi[ée]e?s? r[ée]cemment|\ba chang[ée]|pourquoi .*\b(chang|modifi))", re.I),
     "indice temporel ou d'auteur : l'historique Git est la source de vérité"),
    ("documents", re.compile(r"\b(adr|d[ée]cision d'architecture|sp[ée]cification|exigence|gherkin|"
                             r"crit[eè]res? d'acceptation|ticket|readme|politique)\b", re.I),
     "question sur une décision ou une exigence : documents versionnés"),
    # Guillemets droits ou français seulement : l'apostrophe (« d'hôtel … à l'étranger ») n'est pas une citation.
    ("lexical", re.compile(r"(\"[^\"]{3,}\"|«[^»]{3,}»|\b\w+Exception\b|\b[a-z]+(?:\.[a-z][a-z-]*){2,}\b|"
                           r"\bHTTP ?[45]\d\d\b)"),
     "chaîne exacte, exception ou clé de configuration : recherche lexicale"),
    ("symboles", re.compile(r"(\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b|\b[a-z]+[A-Z][A-Za-z0-9]*\b|\b\w+\(\))"),
     "identifiant de code nommé : recherche de symbole"),
]


class SourceIndisponible(RuntimeError):
    """Source structurellement absente : on dégrade au lieu de réessayer."""


def router_heuristique(question: str, exclues: set[str] | None = None) -> tuple[str | None, str]:
    """Règles déterministes d'abord (gratuites, testables). None = ambigu, le LLM tranche."""
    for source, motif, explication in REGLES_ROUTAGE:
        if source not in (exclues or set()) and motif.search(question):
            return source, explication
    return None, "aucune règle ne s'applique"


def source_suivante(derniere: str, essayees: list[str]) -> str | None:
    return next((s for s in SUITE.get(derniere, []) if s not in essayees), None)


# ---------------------------------------------------------------- termes et couverture
MOTS_VIDES = {"les", "des", "une", "est", "dans", "pour", "par", "sur", "que", "qui", "quoi", "avec", "comment",
              "quel", "quelle", "quels", "quelles", "pas", "plus", "son", "ses", "elle", "il", "ce", "cette",
              "the", "and", "where", "fait", "faire", "sont", "elles", "lorsque", "quand", "pourquoi", "dont"}


def termes(texte: str) -> list[str]:
    t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", texte)  # camelCase -> mots
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [m for m in re.findall(r"[a-z0-9]{3,}", t) if m not in MOTS_VIDES]


MOTS_HISTORIQUE = {"introduit", "introduite", "change", "changé", "changee", "modifie", "modifiee", "commit",
                   "auteur", "quand", "depuis", "historique", "date", "pourquoi", "regression"}


def _racine(m: str) -> str:
    return m[:5] if len(m) >= 5 else m


def _glossaire(glossaire: dict | None) -> dict[str, list[str]]:
    return {t: list(v) for k, v in (glossaire or {}).items() for t in termes(k)[:1]}


def etendre_requete(requete: str, glossaire: dict | None) -> str:
    """Expansion déterministe : un terme métier (« arrondi ») ajoute ses équivalents code (« Math.round »)."""
    g = _glossaire(glossaire)
    ajouts = [x for t in termes(requete) for x in g.get(t, []) if x not in requete]
    return requete if not ajouts else f"{requete} {' '.join(dict.fromkeys(ajouts))}"


# Verbes et mots de la question qui n'en sont pas le sujet (sans accents, minuscules).
MOTS_QUESTION = {"defini", "definie", "definis", "appelle", "appellent", "vient", "viennent", "dit", "disent",
                 "fait", "sert", "renvoie", "renvoient", "existe", "trouve", "situe", "utilise", "explique",
                 "fonctionne", "passe", "quoi", "comment", "pourquoi", "lequel", "laquelle"}
SUJET_RE = re.compile(r"\"([^\"]{3,})\"|«\s*([^»]{3,}?)\s*»|\b([A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+|[a-z]+[A-Z][A-Za-z0-9]*)\b|"
                      r"\b([a-z]+(?:\.[a-z][a-z-]*){2,})\b")


def sujets(question: str) -> list[str]:
    """Identifiants de code, clés de configuration et chaînes entre guillemets cités dans la question."""
    return [next(g for g in m.groups() if g) for m in SUJET_RE.finditer(question)]


def couverture(question: str, preuves: list[dict], source: str | None = None, glossaire: dict | None = None,
               idf=None) -> float:
    """Dans quelle mesure les preuves parlent-elles du SUJET de la question ?

    - La question cite un identifiant, une clé ou une chaîne exacte : on mesure la part de ces sujets
      retrouvés dans les preuves (c'est ce que l'on cherche, le reste est de la syntaxe).
    - Sinon : part des termes de contenu retrouvés, pondérée par leur rareté dans le dépôt (`idf`) :
      un mot courant (« politique », « base ») pèse peu, un terme absent du dépôt (« kubernetes ») pèse lourd,
      si bien qu'une question hors corpus ne passe pas grâce à quelques mots génériques.
    """
    corpus = {_racine(m) for p in preuves for m in termes(f"{p.get('text', '')} {p.get('path', '')} {p.get('symbol') or ''}")}
    sj = sujets(question)
    if sj:
        trouves = [x for x in sj if all(_racine(t) in corpus for t in termes(x))]
        return len(trouves) / len(sj)
    exclus = MOTS_QUESTION | (MOTS_HISTORIQUE if source == "git" else set())
    g = _glossaire(glossaire)
    q = [m for m in dict.fromkeys(termes(question)) if m not in exclus]
    if not q:
        return 1.0

    def couvert(m: str) -> bool:
        return _racine(m) in corpus or any(_racine(x) in corpus for e in g.get(m, []) for x in termes(e))
    poids = {m: (idf(m) if idf else 1.0) for m in q}
    return sum(poids[m] for m in q if couvert(m)) / sum(poids.values())


# ---------------------------------------------------------------- recherche locale (repli)
INCLURE_LOCAL = ("*.java", "*.ts", "*.tsx", "*.js", "*.md", "*.yml", "*.yaml", "*.sql", "*.py")


class RechercheLocale:
    """BM25 minimal sur les fichiers suivis par Git. Sert de repli documenté au lab RAG."""

    def __init__(self, depot: Path, lignes: int = 30, recouvrement: int = 10):
        self.depot = depot
        self.commit = gitutil.head(depot)
        modifies = set(gitutil.git(depot, "diff", "--name-only", "HEAD").splitlines())
        self.chunks: list[dict] = []
        for chemin in gitutil.git(depot, "ls-files").splitlines():
            if not any(fnmatch(chemin, p) for p in INCLURE_LOCAL) or "/.etat/" in chemin:
                continue
            fichier = depot / chemin
            if not fichier.is_file() or fichier.stat().st_size > 200_000:
                continue
            contenu = fichier.read_text(encoding="utf-8", errors="replace").splitlines()
            pas = max(lignes - recouvrement, 1)
            for debut in range(0, max(len(contenu), 1), pas):
                bloc = contenu[debut:debut + lignes]
                if not "".join(bloc).strip():
                    continue
                self.chunks.append({
                    "path": chemin, "start_line": debut + 1, "end_line": debut + len(bloc),
                    "symbol": _symbole(bloc), "commit": self.commit,
                    "modifie_non_commite": chemin in modifies, "text": "\n".join(bloc),
                    "source_type": "doc" if chemin.endswith(".md") else "code",
                    "_termes": Counter(termes("\n".join(bloc) + " " + chemin)),
                })
                if debut + lignes >= len(contenu):
                    break
        self.n = len(self.chunks)
        self.moy = sum(sum(c["_termes"].values()) for c in self.chunks) / (self.n or 1)
        self.df = Counter(t for c in self.chunks for t in c["_termes"])
        self.df_racines = Counter(r for c in self.chunks for r in {_racine(t) for t in c["_termes"]})

    def idf(self, terme: str) -> float:
        """Rareté d'un terme (par racine) dans le dépôt : log((N + 1) / (df + 0,5))."""
        return math.log((self.n + 1) / (self.df_racines.get(_racine(terme), 0) + 0.5))

    def search(self, requete: str, k: int = 5, filtre=None) -> list[dict]:
        q = termes(requete)
        scores = []
        for c in self.chunks:
            if filtre and not filtre(c):
                continue
            tf, longueur, s = c["_termes"], sum(c["_termes"].values()), 0.0
            for t in q:
                if t in tf:
                    idf = math.log(1 + (self.n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                    s += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * longueur / self.moy))
            if s > 0:
                scores.append((s, c))
        scores.sort(key=lambda x: -x[0])
        return [{**{k_: v for k_, v in c.items() if k_ != "_termes"}, "score": round(s, 3)} for s, c in scores[:k]]


def _symbole(lignes: list[str]) -> str | None:
    for l in lignes:
        m = re.search(r"\b(?:class|interface|record|enum|function|def)\s+(\w+)|"
                      r"\b(?:public|private|protected|static)[\w<>\[\], ]*\s(\w+)\s*\(|"
                      r"\b(?:const|let)\s+(\w+)\s*=", l)
        if m:
            return next(g for g in m.groups() if g)
    return None


# ---------------------------------------------------------------- import tolérant du lab RAG
def charger_searcher(cfg: dict):
    """Renvoie (searcher | None, explication). Ne lève jamais : l'absence du lab est un cas prévu."""
    if cfg["rag"].get("activer", "auto") == "non":
        return None, "lab RAG désactivé (config rag.activer=non ou NEOFLOW_RAG=off)"
    chemin = (ICI / cfg["rag"]["chemin_lab"]).resolve()
    if not (chemin / "search.py").is_file():
        return None, f"lab RAG absent ({chemin}/search.py introuvable)"
    if str(chemin) not in sys.path:
        sys.path.insert(0, str(chemin))
    try:
        from search import Searcher  # type: ignore[import-not-found]
        return Searcher(config_path=cfg["rag"].get("config")), f"lab RAG J05 ({chemin})"
    except Exception as exc:  # dépendances manquantes, Qdrant non joignable à l'init...
        return None, f"lab RAG non chargeable : {type(exc).__name__}: {exc}"


# Modes réels de labs/rag/search.py : native (ripgrep), vector, bm25, hybrid (RRF).
MODES_RAG = {"lexical": "bm25", "vectoriel": "vector", "hybride": "hybrid", "documents": "hybrid"}


# ---------------------------------------------------------------- façade
class Sources:
    def __init__(self, depot: str | Path, cfg: dict, panne: int = 0, lenteur_s: float = 0.0):
        self.depot = Path(depot)
        self.cfg = cfg
        self.timeout = float(cfg["limites"]["timeout_source_s"])
        self.panne_restante = panne        # nb d'appels qui échoueront (simulation)
        self.lenteur_s = lenteur_s         # latence injectée (simulation de timeout)
        self.appels = 0
        self._local: RechercheLocale | None = None
        # Un seul thread de travail pour toute la durée de vie : certains clients (Qdrant embarqué,
        # SQLite) exigent d'être utilisés et fermés dans le thread qui les a créés.
        self._executeur = cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="sources")
        self.searcher, self.etat_rag = self._executeur.submit(charger_searcher, cfg).result()
        self.degradations: list[str] = []

    def idf(self, terme: str) -> float:
        """Rareté d'un terme dans le dépôt (index local, construit à la demande)."""
        return self.local.idf(terme)

    @property
    def local(self) -> RechercheLocale:
        if self._local is None:
            self._local = RechercheLocale(self.depot)
        return self._local

    def rechercher(self, source: str, requete: str, k: int = 5) -> list[dict]:
        if source not in SOURCES:
            raise ValueError(f"source inconnue : {source}")
        self.appels += 1
        if self.panne_restante > 0:
            self.panne_restante -= 1
            raise ErreurTransitoire(f"panne simulée du retriever (appel {self.appels})")
        if source in ("lexical", "vectoriel", "hybride", "documents"):
            requete = etendre_requete(requete, self.cfg.get("routage", {}).get("glossaire"))
        resultats = self._avec_timeout(lambda: getattr(self, f"_{source}")(requete, k))
        for r in resultats:
            r["source"] = source
        return resultats

    def _avec_timeout(self, fn):
        """Timeout dur côté appelant. Le travail abandonné peut continuer : pour un vrai arrêt,
        préférer subprocess(timeout=) (sources git) ou un nœud async avec `timeout=` LangGraph."""
        fut = self._executeur.submit(fn)
        try:
            return fut.result(timeout=self.timeout)
        except cf.TimeoutError as exc:
            fut.cancel()
            raise ErreurTransitoire(f"timeout de {self.timeout}s dépassé") from exc
        except TimeoutError as exc:  # sous-processus git tué
            raise ErreurTransitoire(str(exc)) from exc

    def fermer(self) -> None:
        if self.searcher is not None and hasattr(self.searcher, "close"):
            try:
                self._executeur.submit(self.searcher.close).result(timeout=5)
            except Exception:  # fermeture best effort
                pass
        self._executeur.shutdown(wait=False, cancel_futures=True)

    def _latence(self):
        if self.lenteur_s:
            import time
            time.sleep(self.lenteur_s)

    # -- sources ----------------------------------------------------------
    def _rag(self, mode_local: str, requete: str, k: int, filtre=None, source_type: str | None = None) -> list[dict]:
        self._latence()
        if self.searcher is not None:
            try:
                res = self.searcher.search(requete, mode=MODES_RAG[mode_local], k=k, source_type=source_type)
                return [dict(r) for r in res]
            except (ConnectionError, OSError) as exc:
                # labs/rag lève IndexMissingError (OSError) et BackendUnavailableError (ConnectionError)
                self.searcher = None
                self.degradations.append(f"lab RAG indisponible ({type(exc).__name__}: {exc}) -> BM25 local")
            except TypeError as exc:  # API différente de celle attendue
                self.searcher = None
                self.degradations.append(f"API Searcher inattendue ({exc}) -> BM25 local")
        elif mode_local in ("vectoriel", "hybride"):
            msg = f"{mode_local} indisponible ({self.etat_rag}) -> BM25 local"
            if msg not in self.degradations:
                self.degradations.append(msg)
        return self.local.search(requete, k, filtre=filtre)

    def _lexical(self, requete, k):
        return self._rag("lexical", requete, k)

    def _vectoriel(self, requete, k):
        return self._rag("vectoriel", requete, k)

    def _hybride(self, requete, k):
        return self._rag("hybride", requete, k)

    def _documents(self, requete, k):
        return self._rag("documents", requete, k, source_type="doc",
                         filtre=lambda r: str(r.get("path", "")).endswith(".md") or r.get("source_type") == "doc")

    def _symboles(self, requete: str, k: int) -> list[dict]:
        self._latence()
        idents = list(dict.fromkeys(re.findall(r"\b[A-Za-z_]\w*(?=\(\))|\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b|"
                                                r"\b[a-z]+[A-Z][A-Za-z0-9]*\b", requete)))
        if not idents:
            return []
        commit = gitutil.head(self.depot)
        res: list[dict] = []
        for ident in idents[:3]:
            sortie = gitutil.git(self.depot, "grep", "-n", "-I", "-w", "-F", "-e", ident,
                                 timeout=self.timeout, ok_codes=(0, 1))
            for ligne in sortie.splitlines():
                chemin, num, contenu = ligne.split(":", 2)
                definition = bool(re.search(rf"\b(class|interface|record|enum|function|def)\s+{ident}\b|"
                                            rf"\s{ident}\s*\([^;]*\)\s*(\{{|throws|$)", contenu))
                n = int(num)
                lignes = (self.depot / chemin).read_text(encoding="utf-8", errors="replace").splitlines()
                debut, fin = max(n - 3, 1), min(n + 12, len(lignes))
                res.append({"path": chemin, "start_line": debut, "end_line": fin, "symbol": ident,
                            "commit": commit, "score": 2.0 if definition else 1.0,
                            "text": "\n".join(lignes[debut - 1:fin]), "source_type": "code"})
        res.sort(key=lambda r: (-r["score"], r["path"], r["start_line"]))
        vus, uniques = set(), []
        for r in res:
            cle = (r["path"], r["start_line"] // 10)
            if cle not in vus:
                vus.add(cle)
                uniques.append(r)
        return uniques[:k]

    def _git(self, requete: str, k: int) -> list[dict]:
        """Historique : la preuve est le DIFF du fichier le plus pertinent, pas seulement le message."""
        self._latence()
        idents = re.findall(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b|\b[a-z]+[A-Z][A-Za-z0-9]*\b", requete)
        mots = [m for m in termes(requete) if len(m) >= 4 and m not in MOTS_HISTORIQUE][:4]
        fmt = "--format=%H%x1f%an%x1f%ad%x1f%s"
        if idents:
            args = ["log", f"-n{k}", fmt, "--date=short", "-S", idents[0]]
        else:
            args = ["log", f"-n{k}", fmt, "--date=short", "-i", *[f"--grep={m}" for m in mots or ["fix"]]]
        cles = {_racine(m) for m in termes(" ".join(idents + mots))}
        res = []
        for ligne in gitutil.git(self.depot, *args, timeout=self.timeout).splitlines():
            sha, auteur, date, sujet = ligne.split("\x1f")
            patch = gitutil.git(self.depot, "show", "--format=", "-U0", sha, timeout=self.timeout)
            meilleur, score_max = "(commit)", -1
            extrait: list[str] = []
            for bloc in re.split(r"^diff --git ", patch, flags=re.M)[1:]:
                chemin = bloc.split("\n", 1)[0].rsplit(" b/", 1)[-1]
                lignes = [l for l in bloc.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---"))]
                score = len(cles & {_racine(m) for m in termes(" ".join(lignes) + " " + chemin)})
                if score > score_max:
                    meilleur, score_max, extrait = chemin, score, lignes[:12]
            res.append({"path": meilleur, "start_line": 0, "end_line": 0,
                        "symbol": idents[0] if idents else None, "commit": sha, "score": float(score_max),
                        "text": f"{sha[:10]} {date} {auteur} : {sujet}\n" + "\n".join(extrait),
                        "source_type": "git"})
        return res


# ---------------------------------------------------------------- vérification
def verifier_preuves(question: str, preuves: list[dict], depot: str | Path, source: str, cfg: dict,
                     idf=None) -> dict:
    """Contrôles déterministes : quantité, provenance, fraîcheur, couverture de la question.

    Une preuve est OBSOLÈTE si elle a été indexée à un commit antérieur et que le fichier a changé
    depuis : on l'écarte au lieu de la donner au LLM (connaissance périmée = hallucination différée).
    """
    head = gitutil.head(depot)
    fraiches, obsoletes = [], []
    for p in preuves:
        if not p.get("path"):
            continue
        if p.get("stale"):  # le lab RAG J05 compare déjà l'empreinte du fichier indexé
            obsoletes.append({**p, "motif": f"{p['path']} marqué stale par le lab RAG (contenu modifié)"})
            continue
        c = str(p.get("commit") or "").split("+")[0]   # « abc1234+dirty » -> « abc1234 »
        if p.get("source_type") != "git" and re.fullmatch(r"[0-9a-f]{7,40}", c) and not head.startswith(c):
            try:
                change = gitutil.fichier_modifie_depuis(depot, c, p["path"], head)
            except gitutil.ErreurGit:
                change = True  # commit inconnu du dépôt local : on ne peut pas garantir la fraîcheur
            if change:
                obsoletes.append({**p, "motif": f"{p['path']} modifié depuis l'indexation ({c[:10]})"})
                continue
        fraiches.append(p)
    seuil = cfg["preuves"]["min_resultats_git" if source == "git" else "min_resultats"]
    cov = couverture(question, fraiches, source, cfg.get("routage", {}).get("glossaire"), idf)
    suffisant = len(fraiches) >= seuil and cov >= cfg["preuves"]["couverture_min"]
    motif = ("preuves suffisantes" if suffisant else
             f"{len(fraiches)} preuve(s) fraîche(s) (min {seuil}), couverture {cov:.0%} "
             f"(min {cfg['preuves']['couverture_min']:.0%})")
    return {"suffisant": suffisant, "motif": motif, "couverture": round(cov, 2),
            "nb_fraiches": len(fraiches), "obsoletes": obsoletes, "fraiches": fraiches, "head": head}

