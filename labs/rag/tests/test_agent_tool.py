"""Outil RAG de l'agent (contrat neoagent.tools.Tool), sans réseau."""
import re

from agent_tool import INPUT_SCHEMA, rag_tool


def test_contrat_tool(mini_index):
    outil = rag_tool()
    assert re.fullmatch(r"[a-z0-9_]{1,64}", outil.name)
    assert outil.risque == "lecture" and callable(outil.handler)
    assert outil.input_schema is INPUT_SCHEMA and INPUT_SCHEMA["required"] == ["question"]
    assert {"name", "description", "input_schema", "handler", "risque"} <= set(vars(outil))


def test_entree_invalide_renvoie_un_message(mini_index):
    outil = rag_tool()
    for entree in ({}, {"question": "x"}, {"question": "valide ?", "k": 99}, {"question": "ok ok", "mode": "sql"},
                   {"question": "ok ok", "inconnu": 1}):
        assert outil.handler(entree).startswith("Entrée invalide")


def test_reponse_bm25_citee(mini_index):
    sortie = rag_tool().handler({"question": "Où est calculé le niveau de validation ?", "mode": "bm25", "k": 3})
    assert sortie.startswith("<sources_rag") and "DONNÉES" in sortie
    assert re.search(r"\[S1\] \S+:\d+-\d+@\S+", sortie)
    assert "NiveauDemo" in sortie


def test_injection_dans_un_document_neutralisee(mini_index):
    sortie = rag_tool().handler({"question": "note piégée consignes", "mode": "bm25", "k": 5})
    assert sortie.count("</sources_rag>") == 1


def test_mode_vector_degrade_vers_native_sans_qdrant(mini_index):
    sortie = rag_tool().handler({"question": "calculerNiveau", "mode": "vector", "k": 2})
    assert 'mode="native (dégradé' in sortie and "NiveauDemo" in sortie


def test_filtre_source_type(mini_index):
    sortie = rag_tool().handler({"question": "niveau de validation", "mode": "bm25", "source_type": "doc"})
    assert "docs/guide.md" in sortie and ".java:" not in sortie


def test_formateur_branchable(mini_index):
    outil = rag_tool(formateur=lambda q, hits, etat, budget: f"{len(hits)} passage(s), {etat['etat']}")
    assert re.fullmatch(r"[1-9]\d* passage\(s\), à jour", outil.handler({"question": "niveau de validation", "mode": "bm25"}))
