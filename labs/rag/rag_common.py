"""Socle commun du lab RAG NeoFlow (J05).

Configuration, sélection du corpus, métadonnées Git, tokenisation « code-aware »,
embeddings (Ollama ou fastembed) exposés comme un modèle LlamaIndex, client Qdrant
(serveur si joignable, sinon mode embarqué sans Docker).

Ce module n'a pas d'interface en ligne de commande : il est importé par
indexer.py, search.py et eval.py (et par les labs des jours suivants).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

LAB_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = LAB_DIR / "config.yaml"
SCHEMA_VERSION = 1


class IndexMissingError(FileNotFoundError):
    """Index absent ou incomplet (lancer indexer.py). Sous-classe d'OSError : les appelants
    (labs/workflow, labs/mcp) peuvent dégrader proprement vers une autre source."""


class BackendUnavailableError(ConnectionError):
    """Ollama, serveur Qdrant ou Qdrant embarqué (verrou) indisponible."""

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


def load_config(config_path: str | os.PathLike | None = None) -> dict:
    """Charge config.yaml et résout les chemins relatifs au fichier de config.

    Variables d'environnement prioritaires :
      NEOFLOW_RAG_CONFIG  chemin du fichier de configuration
      NEOFLOW_REPO_ROOT   racine du dépôt à indexer (défaut : repo_root du YAML)
      NEOFLOW_RAG_HOME    dossier de stockage de l'index (défaut : storage_dir)
      QDRANT_URL          URL d'un serveur Qdrant (défaut : qdrant.url)
      OLLAMA_HOST         URL d'Ollama (défaut : embedding.ollama.base_url)
    """
    path = Path(config_path or os.environ.get("NEOFLOW_RAG_CONFIG") or DEFAULT_CONFIG).resolve()
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    base = path.parent
    cfg["_config_path"] = str(path)
    root = os.environ.get("NEOFLOW_REPO_ROOT") or cfg.get("repo_root", "../..")
    cfg["_repo_root"] = str((base / root).resolve())
    storage = os.environ.get("NEOFLOW_RAG_HOME") or cfg.get("storage_dir", ".rag_index")
    cfg["_storage_dir"] = str((base / storage).resolve())
    cfg.setdefault("collection", "neoflow")
    cfg.setdefault("corpus", {})
    cfg.setdefault("chunking", {})
    cfg.setdefault("embedding", {})
    cfg.setdefault("qdrant", {})
    cfg.setdefault("search", {})
    return cfg


def charger_composant(cfg: dict, nom: str):
    """Charge un composant écrit en TP, déclaré dans config.yaml > composants.<nom>
    (ou la variable NEOFLOW_RAG_<NOM>) sous la forme « fichier.py:fonction » ou « fichier.py ».
    Le chemin est relatif au fichier de configuration. Renvoie None si rien n'est déclaré :
    le lab utilise alors sa propre implémentation."""
    import importlib.util

    spec = os.environ.get(f"NEOFLOW_RAG_{nom.upper()}") or (cfg.get("composants") or {}).get(nom)
    if not spec:
        return None
    fichier, _, attribut = str(spec).partition(":")
    chemin = (Path(cfg["_config_path"]).parent / fichier).resolve()
    if not chemin.is_file():
        raise FileNotFoundError(f"composant {nom} : fichier {chemin} introuvable (config.yaml > composants)")
    module_spec = importlib.util.spec_from_file_location(f"rag_composant_{nom}", chemin)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    if not attribut:
        return module
    if not hasattr(module, attribut):
        raise AttributeError(f"composant {nom} : {chemin.name} ne définit pas {attribut}")
    return getattr(module, attribut)


def composants_declares(cfg: dict) -> dict[str, str]:
    """Composants de TP actifs (pour les rapports et le manifeste)."""
    declares = {k: v for k, v in (cfg.get("composants") or {}).items() if v}
    for nom in ("chunker_code", "fusion", "metriques", "formateur_outil"):
        if os.environ.get(f"NEOFLOW_RAG_{nom.upper()}"):
            declares[nom] = os.environ[f"NEOFLOW_RAG_{nom.upper()}"]
    return declares


def storage_paths(cfg: dict) -> dict[str, Path]:
    store = Path(cfg["_storage_dir"])
    return {
        "dir": store,
        "manifest": store / "manifest.json",
        "chunks": store / "chunks.jsonl",
        "qdrant": store / "qdrant",
    }


# --------------------------------------------------------------------------- #
# Git : commit, branche, fichiers modifiés, dernier commit par fichier
# --------------------------------------------------------------------------- #


def _git(root: str | Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=20, check=True,
        )
        return out.stdout
    except (OSError, subprocess.SubprocessError):
        return None


@dataclass
class GitInfo:
    is_repo: bool = False
    commit: str = "nogit"          # sha court du HEAD au moment de l'indexation
    commit_full: str = ""
    branch: str = "nogit"
    remote: str = ""
    dirty_files: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "is_repo": self.is_repo, "commit": self.commit, "commit_full": self.commit_full,
            "branch": self.branch, "remote": self.remote, "dirty_files": sorted(self.dirty_files),
        }


def git_info(root: str | Path) -> GitInfo:
    if (_git(root, "rev-parse", "--is-inside-work-tree") or "").strip() != "true":
        return GitInfo()
    info = GitInfo(is_repo=True)
    full = (_git(root, "rev-parse", "HEAD") or "").strip()
    if full:
        info.commit_full = full
        info.commit = full[:7]
    else:  # dépôt sans commit
        info.commit = "nocommit"
    info.branch = (_git(root, "rev-parse", "--abbrev-ref", "HEAD") or "").strip() or "detached"
    info.remote = (_git(root, "config", "--get", "remote.origin.url") or "").strip()
    changed = (_git(root, "diff", "--name-only", "--relative", "HEAD") or "") if full else ""
    untracked = _git(root, "ls-files", "--others", "--exclude-standard") or ""
    info.dirty_files = {line.strip() for line in (changed + "\n" + untracked).splitlines() if line.strip()}
    return info


def file_last_commit(root: str | Path, rel_path: str) -> tuple[str, str]:
    """Dernier commit ayant modifié le fichier : (sha court, date ISO). Vide hors Git."""
    out = _git(root, "log", "-1", "--format=%h|%cI", "--", rel_path)
    if not out or "|" not in out:
        return "", ""
    sha, date = out.strip().split("|", 1)
    return sha, date


def head_commit(root: str | Path) -> str:
    out = _git(root, "rev-parse", "--short=7", "HEAD")
    return out.strip() if out else "nogit"


# --------------------------------------------------------------------------- #
# Corpus : liste blanche, .gitignore, binaires, fichiers générés, taille
# --------------------------------------------------------------------------- #

ALWAYS_SKIP_DIRS = {
    ".git", "node_modules", "target", "dist", "build", ".venv", "venv", "__pycache__",
    ".rag_index", ".idea", ".vscode", "coverage", ".next", ".turbo", "playwright-report",
    "test-results", ".gradle", ".mvn",
}
DOC_EXTENSIONS = {".md", ".markdown", ".adoc", ".txt", ".rst"}
GENERATED_MARKERS = ("@generated", "do not edit", "auto-generated", "autogenerated", "generated by")


def _spec(lines: Iterable[str]):
    import pathspec  # import local : pathspec n'est requis que pour l'indexation/natif

    return pathspec.GitIgnoreSpec.from_lines([l for l in lines if l and not l.startswith("#")])


def _candidate_files(root: Path) -> tuple[list[str], str]:
    """Fichiers candidats. Dans un dépôt Git : suivis + non suivis non ignorés
    (git applique tous les .gitignore). Sinon : parcours du disque + .gitignore racine."""
    out = _git(root, "ls-files", "--cached", "--others", "--exclude-standard")
    if out is not None and (_git(root, "rev-parse", "--is-inside-work-tree") or "").strip() == "true":
        files = [l.strip() for l in out.splitlines() if l.strip()]
        return sorted(set(files)), "git ls-files"
    gitignore = root / ".gitignore"
    ignore = _spec(gitignore.read_text(encoding="utf-8", errors="replace").splitlines()) if gitignore.exists() else None
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ALWAYS_SKIP_DIRS]
        for name in filenames:
            rel = Path(dirpath, name).relative_to(root).as_posix()
            if ignore is not None and ignore.match_file(rel):
                continue
            files.append(rel)
    return sorted(files), "parcours disque + .gitignore"


def _is_binary(sample: bytes) -> bool:
    return b"\x00" in sample


def _is_generated(rel: str, head: str, text_sample: str) -> bool:
    low = head.lower()
    if any(marker in low for marker in GENERATED_MARKERS):
        return True
    if rel.endswith((".min.js", ".min.css", ".map", ".lock")) or rel.endswith("package-lock.json"):
        return True
    lines = text_sample.splitlines()
    if lines and rel.endswith((".js", ".css")) and sum(len(l) for l in lines) / len(lines) > 300:
        return True  # code minifié
    return False


@dataclass
class CorpusSelection:
    files: list[str]
    skipped: dict[str, list[str]]
    source: str


def select_corpus(cfg: dict) -> CorpusSelection:
    """Applique : candidats (git/.gitignore) -> include -> exclude -> taille -> binaire -> généré."""
    root = Path(cfg["_repo_root"])
    corpus = cfg.get("corpus", {})
    include = _spec(corpus.get("include", ["**/*"]))
    exclude = _spec(corpus.get("exclude", []))
    max_bytes = int(corpus.get("max_file_kb", 256)) * 1024
    candidates, source = _candidate_files(root)
    skipped: dict[str, list[str]] = {"hors_liste_blanche": [], "exclu": [], "taille": [], "binaire": [], "genere": []}
    kept: list[str] = []
    for rel in candidates:
        if any(part in ALWAYS_SKIP_DIRS for part in Path(rel).parts[:-1]):
            skipped["exclu"].append(rel)
            continue
        if not include.match_file(rel):
            skipped["hors_liste_blanche"].append(rel)
            continue
        if exclude.match_file(rel):
            skipped["exclu"].append(rel)
            continue
        path = root / rel
        try:
            size = path.stat().st_size
        except OSError:
            continue  # supprimé mais encore dans l'index Git
        if size > max_bytes:
            skipped["taille"].append(rel)
            continue
        with open(path, "rb") as fh:
            sample = fh.read(8192)
        if _is_binary(sample):
            skipped["binaire"].append(rel)
            continue
        text_sample = sample.decode("utf-8", errors="replace")
        if _is_generated(rel, "\n".join(text_sample.splitlines()[:8]), text_sample):
            skipped["genere"].append(rel)
            continue
        kept.append(rel)
    return CorpusSelection(files=kept, skipped=skipped, source=source)


def source_type_of(rel_path: str) -> str:
    return "doc" if Path(rel_path).suffix.lower() in DOC_EXTENSIONS else "code"


def acl_of(rel_path: str, cfg: dict) -> str:
    """Étiquette d'accès d'un fichier (première règle qui correspond, sinon 'projet')."""
    for rule in cfg.get("acl", {}).get("rules", []) or []:
        if _spec(rule.get("paths", [])).match_file(rel_path):
            return str(rule.get("label", "projet"))
    return str(cfg.get("acl", {}).get("default", "projet"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Masquage des secrets avant indexation
# --------------------------------------------------------------------------- #

_SECRET_LINE = re.compile(
    r"""^(?P<key>\s*[-\w.]*(?:api[-_.]?key|secret|password|passwd|pwd|mot[-_.]?de[-_.]?passe|mdp|token|credentials?|private[-_.]?key)[-\w.]*
        \s*[:=]\s*)(?P<val>["']?[^\s"'#]{4,}["']?)""",
    re.IGNORECASE | re.VERBOSE,
)
_SECRET_TOKENS = re.compile(r"(sk-ant-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[bap]-[A-Za-z0-9-]{10,})")


def redact_secrets(text: str) -> tuple[str, int]:
    """Remplace les valeurs ressemblant à des secrets par ***MASQUE***.
    Les numéros de ligne sont conservés (remplacement dans la ligne)."""
    count = 0
    out_lines = []
    for line in text.split("\n"):
        m = _SECRET_LINE.match(line)
        if m and not m.group("val").strip("\"'").startswith("${"):
            line = line[: m.start("val")] + "***MASQUE***" + line[m.end("val"):]
            count += 1
        line, n = _SECRET_TOKENS.subn("***MASQUE***", line)
        count += n
        out_lines.append(line)
    return "\n".join(out_lines), count


# --------------------------------------------------------------------------- #
# Tokenisation adaptée au code (BM25) et termes de recherche (natif)
# --------------------------------------------------------------------------- #

STOPWORDS = set(
    """
    a au aux avec ce ces cet cette dans de des du elle en est et etre il ils je la le les leur lui
    ma mais me meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta
    te tes toi ton tu un une vos votre vous y quel quelle quels quelles comment ou quoi combien
    pourquoi quand donc alors ainsi est-ce sont ont fait faire peut peuvent doit doivent etc tout
    tous toute toutes entre sans sous lors chez selon via apres avant plus moins tres trop bien
    the of and or to in is are be for on with as by an at from this that it its which what where
    how when why does do can should into not no yes if then else
    public private protected static final void return new import package class interface extends
    implements this super null true false var let const function export default async await try
    catch throw throws string int double boolean long
    """.split()
)

_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_]+")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-zà-öø-ÿ]+|[A-Z]+|\d+")


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


try:  # stemmer Snowball (dépendance de fastembed, aussi listée dans pyproject.toml)
    from py_rust_stemmers import SnowballStemmer

    _STEMMER = SnowballStemmer("french")

    def stem(word: str) -> str:
        return _STEMMER.stem_word(word)
except Exception:  # pragma: no cover - repli minimal
    def stem(word: str) -> str:
        for suffix in ("ements", "ement", "ations", "ation", "ees", "ee", "es", "s", "e"):
            if len(word) > len(suffix) + 3 and word.endswith(suffix):
                return word[: -len(suffix)]
        return word


def split_identifier(token: str) -> list[str]:
    """determinerNiveau -> [determiner, Niveau] ; NIVEAU_MAX -> [NIVEAU, MAX]."""
    parts: list[str] = []
    for piece in token.split("_"):
        parts.extend(_CAMEL.findall(piece) or ([piece] if piece else []))
    return parts


def tokenize(text: str) -> list[str]:
    """Tokens BM25 : identifiants découpés (camelCase, snake_case) + identifiant complet,
    minuscules, sans accents, racinisés, sans mots vides ni mots-clés du langage."""
    tokens: list[str] = []
    for raw in _WORD.findall(text):
        parts = split_identifier(raw)
        candidates = [raw] + parts if len(parts) > 1 else [raw]
        for part in candidates:
            word = strip_accents(part.lower())
            if len(word) < 2 or word in STOPWORDS or word.isdigit() and len(word) < 3:
                continue
            tokens.append(stem(word))
    return tokens


_ACCENT_CLASSES = {"a": "[aàâä]", "e": "[eéèêë]", "i": "[iîï]", "o": "[oôö]", "u": "[uùûü]", "c": "[cç]"}


def query_terms(query: str) -> list[dict]:
    """Termes pour la recherche native (grep) : un identifiant est cherché tel quel,
    un mot français par sa racine, insensible aux accents (calculé -> c[aàâä]lc[uùûü]l)."""
    terms: list[dict] = []
    seen: set[str] = set()
    for raw in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_]+(?:\.[A-Za-z_][A-Za-z0-9_]*)*", query):
        is_identifier = bool(re.search(r"[a-z][A-Z]|_|\.|\d", raw)) or (raw[:1].isupper() and len(raw) > 1 and raw[1:].lower() != raw[1:])
        plain = strip_accents(raw.lower())
        if not is_identifier and (len(plain) < 3 or plain in STOPWORDS):
            continue
        if is_identifier:
            pattern = re.escape(raw)
            key = raw.lower()
        else:
            root = stem(plain)
            root = root if len(root) >= 4 else plain
            pattern = "".join(_ACCENT_CLASSES.get(ch, re.escape(ch)) for ch in root)
            key = root
        if key in seen:
            continue
        seen.add(key)
        terms.append({"term": raw, "key": key, "regex": pattern, "identifier": is_identifier})
    return terms


# --------------------------------------------------------------------------- #
# Embeddings : Ollama (nomic-embed-text) sinon fastembed, interface LlamaIndex
# --------------------------------------------------------------------------- #


def ollama_available(base_url: str, model: str, timeout: float = 1.5) -> bool:
    import httpx

    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        names = {m.get("name", "") for m in resp.json().get("models", [])}
        return any(n == model or n.split(":")[0] == model.split(":")[0] for n in names)
    except Exception:
        return False


def resolve_embedding(cfg: dict, forced: dict | None = None) -> dict:
    """Choisit le fournisseur d'embeddings. 'forced' = celui enregistré dans le manifeste
    de l'index : à la recherche, on réutilise TOUJOURS le modèle de l'indexation."""
    emb = cfg.get("embedding", {})
    ollama_cfg = emb.get("ollama", {})
    base_url = os.environ.get("OLLAMA_HOST") or ollama_cfg.get("base_url", "http://localhost:11434")
    if base_url and not base_url.startswith("http"):
        base_url = "http://" + base_url
    common = {
        "query_prefix": emb.get("query_prefix", "search_query: "),
        "document_prefix": emb.get("document_prefix", "search_document: "),
        "batch_size": int(emb.get("batch_size", 32)),
    }
    if forced:
        spec = dict(common, **forced)
        if spec["provider"] == "ollama":
            spec["base_url"] = base_url
        return spec
    provider = emb.get("provider", "auto")
    if provider in ("auto", "ollama"):
        model = ollama_cfg.get("model", "nomic-embed-text")
        if ollama_available(base_url, model):
            return dict(common, provider="ollama", model=model, base_url=base_url)
        if provider == "ollama":
            raise BackendUnavailableError(f"Ollama injoignable sur {base_url} ou modèle {model} absent (ollama pull {model}).")
    fe = emb.get("fastembed", {})
    return dict(common, provider="fastembed", model=fe.get("model", "nomic-ai/nomic-embed-text-v1.5-Q"),
                cache_dir=fe.get("cache_dir"))


def make_embed_model(spec: dict):
    """Fabrique un modèle d'embedding LlamaIndex (BaseEmbedding) à partir d'une spec résolue."""
    from llama_index.core.base.embeddings.base import BaseEmbedding
    from pydantic import PrivateAttr

    class NeoflowEmbedding(BaseEmbedding):
        """Embeddings locaux avec préfixes de tâche (nomic : search_query / search_document)."""

        provider: str = "ollama"
        base_url: str | None = None
        query_prefix: str = ""
        document_prefix: str = ""
        cache_dir: str | None = None
        _fastembed: Any = PrivateAttr(default=None)

        def _embed(self, texts: list[str]) -> list[list[float]]:
            if self.provider == "ollama":
                import httpx

                try:
                    resp = httpx.post(
                        f"{self.base_url.rstrip('/')}/api/embed",
                        json={"model": self.model_name, "input": texts, "truncate": True},
                        timeout=300,
                    )
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    raise BackendUnavailableError(
                        f"Ollama ({self.base_url}, modèle {self.model_name}) indisponible : {exc}. "
                        "L'index a été construit avec ce modèle : relancer Ollama ou réindexer.") from exc
                return resp.json()["embeddings"]
            if self._fastembed is None:
                from fastembed import TextEmbedding

                kwargs = {"cache_dir": self.cache_dir} if self.cache_dir else {}
                self._fastembed = TextEmbedding(model_name=self.model_name, **kwargs)
            return [vec.tolist() for vec in self._fastembed.embed(texts, batch_size=self.embed_batch_size)]

        def _get_query_embedding(self, query: str) -> list[float]:
            return self._embed([self.query_prefix + query])[0]

        def _get_text_embedding(self, text: str) -> list[float]:
            return self._embed([self.document_prefix + text])[0]

        def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
            return self._embed([self.document_prefix + t for t in texts])

        async def _aget_query_embedding(self, query: str) -> list[float]:
            return self._get_query_embedding(query)

        async def _aget_text_embedding(self, text: str) -> list[float]:
            return self._get_text_embedding(text)

    return NeoflowEmbedding(
        model_name=spec["model"], provider=spec["provider"], base_url=spec.get("base_url"),
        query_prefix=spec.get("query_prefix", ""), document_prefix=spec.get("document_prefix", ""),
        cache_dir=spec.get("cache_dir"), embed_batch_size=spec.get("batch_size", 32),
    )


# --------------------------------------------------------------------------- #
# Qdrant : serveur si joignable (profil docker 'ia'), sinon mode embarqué local
# --------------------------------------------------------------------------- #


def qdrant_client(cfg: dict, forced_mode: dict | None = None):
    """Retourne (client, description). forced_mode = mode enregistré dans le manifeste."""
    from qdrant_client import QdrantClient

    qcfg = cfg.get("qdrant", {})
    url = os.environ.get("QDRANT_URL") or qcfg.get("url")
    want_server = qcfg.get("prefer_server", True)
    if forced_mode:
        want_server = forced_mode.get("mode") == "server"
        url = os.environ.get("QDRANT_URL") or forced_mode.get("url") or url
    if url and want_server:
        try:
            client = QdrantClient(url=url, timeout=3, check_compatibility=False)
            client.get_collections()
            return client, {"mode": "server", "url": url}
        except Exception as exc:
            if forced_mode and forced_mode.get("mode") == "server":
                raise BackendUnavailableError(f"Index construit sur le serveur Qdrant {url}, injoignable : {exc}") from exc
    path = storage_paths(cfg)["qdrant"]
    path.mkdir(parents=True, exist_ok=True)
    try:
        return QdrantClient(path=str(path)), {"mode": "embedded", "path": str(path)}
    except Exception as exc:  # verrou : un seul processus à la fois en mode embarqué
        raise BackendUnavailableError(
            f"Qdrant embarqué {path} indisponible ({exc}). Un autre processus (indexer, serveur MCP, "
            "workflow) utilise-t-il l'index ? En usage concurrent, démarrer le serveur Qdrant.") from exc


# --------------------------------------------------------------------------- #
# Manifeste et chunks persistés
# --------------------------------------------------------------------------- #


def read_manifest(cfg: dict) -> dict | None:
    path = storage_paths(cfg)["manifest"]
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(cfg: dict, manifest: dict) -> None:
    path = storage_paths(cfg)["manifest"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def read_chunks(cfg: dict) -> list[dict]:
    path = storage_paths(cfg)["chunks"]
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_chunks(cfg: dict, chunks: list[dict]) -> None:
    path = storage_paths(cfg)["chunks"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")


# Métadonnées ajoutées au texte indexé par BM25 (le chemin et les membres deviennent cherchables).
# Pour l'embedding, la liste est réglable : embedding.metadata_keys dans config.yaml.
# Changer l'une ou l'autre impose une réindexation complète.
EMBED_KEYS = ("path", "symbol", "kind", "members", "doc_title")


def embedding_metadata_keys(cfg: dict) -> list[str]:
    return list(cfg.get("embedding", {}).get("metadata_keys", EMBED_KEYS))


def embed_text(record: dict) -> str:
    head = "\n".join(f"{k}: {record[k]}" for k in EMBED_KEYS if record.get(k))
    return f"{head}\n\n{record['text']}"


def citation(path: str, start: int, end: int, commit: str) -> str:
    return f"{path}:{start}-{end}@{commit}"


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil(pct / 100 * len(ordered)) - 1))
    return ordered[idx]
