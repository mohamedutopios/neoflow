"""Branchement des composants écrits en TP (config.yaml > composants)."""
import pytest

import eval as ev
import rag_metriques
from rag_chunker import chunk_file
from rag_common import charger_composant, load_config
from search import rrf


def cfg_avec(tmp_path, **composants):
    cfg = load_config()
    cfg["_config_path"] = str(tmp_path / "config.yaml")
    cfg["composants"] = composants
    return cfg


def test_rien_de_declare(tmp_path):
    assert charger_composant(cfg_avec(tmp_path), "fusion") is None


def test_chargement_fichier_fonction(tmp_path):
    (tmp_path / "tp").mkdir()
    (tmp_path / "tp/fusion.py").write_text("def rrf(classements, k=60, poids=None):\n    return [('x', 1.0)]\n")
    fn = charger_composant(cfg_avec(tmp_path, fusion="tp/fusion.py:rrf"), "fusion")
    assert fn({}) == [("x", 1.0)]


def test_erreurs_explicites(tmp_path):
    with pytest.raises(FileNotFoundError):
        charger_composant(cfg_avec(tmp_path, fusion="absent.py:rrf"), "fusion")
    (tmp_path / "m.py").write_text("x = 1\n")
    with pytest.raises(AttributeError):
        charger_composant(cfg_avec(tmp_path, fusion="m.py:rrf"), "fusion")


SRC = "public class A {\n    void f() {}\n}\n"


def test_chunker_tp_qui_rend_la_main():
    lab = chunk_file("A.java", SRC, {})
    assert chunk_file("A.java", SRC, {}, lambda *a: None) == lab


def test_chunker_tp_utilise_et_controle():
    custom = lambda chemin, source, langage, opts: [{"start_line": 1, "end_line": 3, "symbol": "A", "kind": "class"}]
    chunks = chunk_file("A.java", SRC, {}, custom)
    assert [(c.start_line, c.end_line, c.symbol, c.kind) for c in chunks] == [(1, 3, "A", "class")]
    assert chunks[0].text.startswith("public class A")
    with pytest.raises(ValueError):
        chunk_file("A.java", SRC, {}, lambda *a: [{"start_line": 0, "end_line": 99, "symbol": "A", "kind": "x"}])


def test_metriques_tp_prioritaires_fonction_par_fonction():
    class Module:
        @staticmethod
        def recall_at_k(trouves, attendus, k):
            return 0.42
    m = ev.Metriques(Module)
    assert m.recall_at_k([], {"a"}, 5) == 0.42 and m.source["recall_at_k"] == "tp"
    assert m.mrr is rag_metriques.mrr and m.source["mrr"] == "lab"


def test_rrf_du_lab():
    fused = rrf({"vector": ["a", "b"], "bm25": ["b", "c"]}, k=60)
    assert [d for d, _, _ in fused] == ["b", "a", "c"]
    assert fused[0][2] == {"vector": 2, "bm25": 1}
