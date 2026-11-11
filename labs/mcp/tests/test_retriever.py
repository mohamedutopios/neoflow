"""Retriever : provenance, repli lexical, import tolérant du lab J05, refus de lecture, audit."""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

import retriever_server as rs
from conftest import LAB, appeler, texte, dernier_appel


@pytest.fixture(autouse=True)
def reinitialiser_rag():
    rs._etat.searcher, rs._etat.raison, rs._etat.essai = None, None, 0.0
    chemins = list(sys.path)
    sys.modules.pop("search", None)
    yield
    sys.modules.pop("search", None)
    sys.path[:] = chemins


def test_search_code_mode_lexical_avec_provenance(journal):
    res = appeler(rs.mcp, "search_code", {"query": "calcul du niveau de validation CircuitValidationService"})
    assert not res.is_error
    data = res.structured_content
    assert data["retrieval_mode"] == "lexical-local"
    assert data["trust"] == "untrusted"
    premier = data["results"][0]
    assert premier["path"].endswith("CircuitValidationService.java")
    assert premier["citation"] == f"{premier['path']}:{premier['start_line']}-{premier['end_line']}@{premier['commit']}"
    assert len(premier["commit"]) >= 7
    evt = dernier_appel(journal)
    assert evt["decision"] == "allowed" and evt["tool"] == "search_code" and evt["sources"]


def test_search_docs_ne_renvoie_que_de_la_doc_et_signale_l_injection():
    data = appeler(rs.mcp, "search_docs", {"query": "export CSV demandes"}).structured_content
    assert data["results"] and all(r["source_type"] == "doc" for r in data["results"])
    assert "commentaire_cache_pour_ia" in data["injection_flags"]


def test_fichier_sensible_jamais_renvoye_par_la_recherche():
    data = appeler(rs.mcp, "search_code", {"query": "ANTHROPIC_API_KEY"}).structured_content
    assert all(not r["path"].endswith(".env") for r in data["results"])


@pytest.mark.parametrize("chemin, code", [
    (".env", "fichier_sensible"),
    ("../../etc/passwd", "traversee"),
    ("/etc/passwd", "chemin_absolu"),
    ("docs/lien-externe/hosts", "hors_depot"),
    ("docs/inexistant.md", "introuvable"),
])
def test_get_chunk_refuse(chemin, code, journal):
    res = appeler(rs.mcp, "get_chunk", {"path": chemin, "start_line": 1, "end_line": 5})
    assert res.is_error and f"REFUS [{code}]" in texte(res)
    evt = dernier_appel(journal)
    assert evt["decision"] == "refused" and evt["reason"] == code


def test_get_chunk_lignes_exactes_et_secret_masque():
    res = appeler(rs.mcp, "get_chunk", {"path": "backend/src/main/resources/application.yml", "start_line": 1, "end_line": 50})
    data = res.structured_content
    assert data["end_line"] == data["total_lines"]
    assert "FAUX-JETON-DEMO" not in data["text"] and "[MASQUÉ]" in data["text"]
    assert data["citation"].startswith("backend/src/main/resources/application.yml:1-")


def test_get_chunk_a_un_commit_et_bornes():
    data = appeler(rs.mcp, "search_code", {"query": "CircuitValidationService"}).structured_content
    commit = data["head_commit"]
    res = appeler(rs.mcp, "get_chunk", {"path": data["results"][0]["path"], "start_line": 3, "end_line": 4, "commit": commit})
    assert res.structured_content["text"].splitlines()[0].strip().startswith("3 |")
    res = appeler(rs.mcp, "get_chunk", {"path": "README.md", "start_line": 1, "end_line": 900})
    assert res.structured_content["end_line"] <= 200


def test_arguments_invalides_refuses(journal):
    res = appeler(rs.mcp, "search_code", {"query": "x", "k": 50})
    assert res.is_error
    assert dernier_appel(journal)["reason"] == "arguments_invalides"


def _faux_lab_rag(dossier: Path, hybride_en_panne: bool) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "search.py").write_text(textwrap.dedent(f"""
        class Searcher:
            def __init__(self, config_path=None):
                self.config_path = config_path
            def search(self, query, mode="hybrid", k=5, *, source_type=None):
                if mode == "hybrid" and {hybride_en_panne!r}:
                    raise FileNotFoundError("Index absent : lancer indexer.py")
                return [
                    {{"path": "backend/src/main/java/com/neosoft/neoflow/validation/CircuitValidationService.java",
                      "start_line": 3, "end_line": 8, "symbol": "calculerNiveau", "commit": "0000000",
                      "score": 0.91, "text": "public int calculerNiveau(...)", "source_type": "code", "stale": False}},
                    {{"path": ".env", "start_line": 1, "end_line": 1, "symbol": "", "commit": "0000000",
                      "score": 0.5, "text": "SECRET", "source_type": "code"}},
                ][:k]
            def info(self):
                return {{"indexed_commit": "0000000", "index_behind_head": True}}
    """), encoding="utf-8")
    return dossier


def test_mode_rag_via_searcher_j05(tmp_path, monkeypatch, journal):
    monkeypatch.setenv("NEOFLOW_RAG_MODE", "auto")
    monkeypatch.setenv("NEOFLOW_RAG_DIR", str(_faux_lab_rag(tmp_path / "rag", hybride_en_panne=False)))
    data = appeler(rs.mcp, "search_code", {"query": "niveau de validation", "k": 5}).structured_content
    assert data["retrieval_mode"] == "rag:hybrid" and data["degraded_reason"] is None
    assert [r["symbol"] for r in data["results"]] == ["calculerNiveau"]
    assert data["filtered_sensitive"] == 1          # .env écarté même s'il sort de l'index
    assert data["results"][0]["stale"] is None       # commit inconnu du dépôt : fraîcheur non garantie


def test_repli_native_si_index_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("NEOFLOW_RAG_MODE", "auto")
    monkeypatch.setenv("NEOFLOW_RAG_DIR", str(_faux_lab_rag(tmp_path / "rag2", hybride_en_panne=True)))
    data = appeler(rs.mcp, "search_code", {"query": "niveau de validation"}).structured_content
    assert data["retrieval_mode"] == "rag:native"
    assert "Index absent" in data["degraded_reason"]


def test_repli_lexical_si_module_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("NEOFLOW_RAG_MODE", "auto")
    monkeypatch.setenv("NEOFLOW_RAG_DIR", str(tmp_path / "pas-de-rag"))
    data = appeler(rs.mcp, "search_code", {"query": "CircuitValidationService"}).structured_content
    assert data["retrieval_mode"] == "lexical-local"
    assert "introuvable" in data["degraded_reason"]


def test_mode_rag_exige_mais_absent_refuse(tmp_path, monkeypatch):
    monkeypatch.setenv("NEOFLOW_RAG_MODE", "rag")
    monkeypatch.setenv("NEOFLOW_RAG_DIR", str(tmp_path / "pas-de-rag"))
    res = appeler(rs.mcp, "search_code", {"query": "CircuitValidationService"})
    assert res.is_error and "rag_indisponible" in texte(res)


def test_integration_lab_j05_reel_mode_natif(depot, monkeypatch):
    """Intégration avec le vrai labs/rag (J05) si ses dépendances minimales sont installées (extra « rag »)."""
    rag_dir = LAB.parent / "rag"
    if not (rag_dir / "search.py").exists():
        pytest.skip("labs/rag absent")
    pytest.importorskip("yaml")
    pytest.importorskip("pathspec")
    monkeypatch.setenv("NEOFLOW_RAG_MODE", "auto")
    monkeypatch.setenv("NEOFLOW_RAG_DIR", str(rag_dir))
    monkeypatch.setenv("NEOFLOW_REPO_ROOT", str(depot))
    monkeypatch.setenv("NEOFLOW_RAG_HOME", str(depot / ".rag_index_absent"))
    data = appeler(rs.mcp, "search_code", {"query": "CircuitValidationService calculerNiveau", "mode": "native"}).structured_content
    assert data["retrieval_mode"] == "rag:native", data["degraded_reason"]
    assert data["results"] and data["results"][0]["path"].endswith("CircuitValidationService.java")


def test_ressource_statut_et_prompt():
    import asyncio
    from fastmcp import Client

    async def _run():
        async with Client(rs.mcp) as c:
            statut = await c.read_resource("rag://statut")
            prompts = await c.list_prompts()
            return statut[0].text, [p.name for p in prompts]
    statut, prompts = asyncio.run(_run())
    assert '"mode_configure": "lexical"' in statut
    assert prompts == ["question_codebase"]
