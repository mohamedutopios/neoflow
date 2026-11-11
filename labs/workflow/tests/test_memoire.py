"""Mémoire gouvernée : provenance, portée, expiration, invalidation et relocalisation via Git."""
from __future__ import annotations

from datetime import timedelta

import pytest

from config import charger
from memoire import MemoireRefusee, StoreMemoire, maintenant

LEGACY = "backend/src/main/java/com/neosoft/neoflow/legacy/RegleValidationLegacy.java"
ADR = "docs/adr/ADR-001-circuit-validation.md"


@pytest.fixture
def store(etat):
    return StoreMemoire(etat / "memoire.db", charger())


def fait_dsi(store, depot, lignes="20-24"):
    return store.ajouter("semantique", "Pour MATERIEL_IT, la DSI est comparée par référence (==) : bug latent",
                         "projet:neoflow", source=f"{LEGACY}@HEAD:{lignes}", depot=depot.racine)


@pytest.mark.parametrize("kwargs,motif", [
    ({"type": "semantique", "contenu": "fait sans source", "portee": "projet:neoflow"}, "provenance"),
    ({"type": "procedurale", "contenu": "lancer ./mvnw test", "portee": "projet:neoflow"}, "provenance"),
    ({"type": "episodique", "contenu": "clé sk-ant-api03-abcdefghijklmnop", "portee": "projet:neoflow"}, "secret"),
    ({"type": "episodique", "contenu": "password = Neoflow2026!", "portee": "projet:neoflow"}, "secret"),
    ({"type": "episodique", "contenu": "ok", "portee": "neoflow"}, "portée"),
    ({"type": "intuition", "contenu": "ok", "portee": "projet:neoflow"}, "type"),
])
def test_ecritures_refusees_par_la_politique(store, kwargs, motif):
    with pytest.raises(MemoireRefusee, match=motif):
        store.ajouter(kwargs.pop("type"), kwargs.pop("contenu"), kwargs.pop("portee"), **kwargs)


def test_head_resolu_en_sha_et_extrait_empreinte(store, depot):
    m = fait_dsi(store, depot)
    assert m.source_commit == depot.git("rev-parse", "HEAD") and len(m.source_commit) == 40
    assert "departement == DSI" in m.extrait and m.empreinte


def test_provenance_sans_depot_exige_un_sha(store):
    with pytest.raises(MemoireRefusee, match="SHA"):
        store.ajouter("semantique", "x", "projet:neoflow", source=f"{LEGACY}@HEAD:1-2")


def test_provenance_inverifiable_refusee(store, depot):
    with pytest.raises(MemoireRefusee, match="invérifiable"):
        store.ajouter("semantique", "x", "projet:neoflow", source="src/Inexistant.java@HEAD:1-2", depot=depot.racine)


def test_isolation_des_portees(store, depot):
    store.ajouter("episodique", "Le client Acme impose Java 17 sur ses serveurs", "client:acme",
                  source=f"{ADR}@HEAD", depot=depot.racine)
    fait_dsi(store, depot)
    valides, _ = store.rechercher("Java DSI serveurs client", ["projet:neoflow"])
    assert all(m.portee == "projet:neoflow" for m in valides)
    with pytest.raises(ValueError):
        store.rechercher("Java", [])


def test_expiration_et_purge(store, depot):
    passe = maintenant() - timedelta(days=40)
    store.ajouter("episodique", "Revue de la PR 12 sur le circuit de validation", "projet:neoflow",
                  source=f"{ADR}@HEAD", depot=depot.racine, now=passe)  # TTL épisodique 30 j
    valides, ecartees = store.rechercher("revue circuit validation", ["projet:neoflow"])
    assert valides == [] and ecartees[0][1] == "expirée"
    store.ajouter("episodique", "Autre épisode expiré", "projet:neoflow", source=f"{ADR}@HEAD",
                  depot=depot.racine, now=passe)
    assert store.purger() == 1


def test_invalidation_quand_les_lignes_citees_changent(store, depot):
    m = fait_dsi(store, depot)
    c1 = depot.git("rev-parse", "HEAD")
    depot.ecrire(LEGACY, depot.lire(LEGACY).replace("departement == DSI", "DSI.equals(departement)"))
    depot.commit("fix: comparaison de chaînes")
    rapport = store.invalider_depuis_git(depot.racine, c1)
    assert [r["id"] for r in rapport["invalidees"]] == [m.id]
    assert store.get(m.id).statut == "invalide"
    assert store.rechercher("DSI MATERIEL_IT référence", ["projet:neoflow"])[0] == []


def test_relocalisation_quand_le_code_cite_est_deplace(store, depot):
    m = fait_dsi(store, depot)
    c1 = depot.git("rev-parse", "HEAD")
    depot.ecrire(LEGACY, depot.lire(LEGACY).replace("public class RegleValidationLegacy {",
                                                    "/** Javadoc ajoutée. */\n\npublic class RegleValidationLegacy {"))
    c2 = depot.commit("docs: javadoc")
    rapport = store.invalider_depuis_git(depot.racine, c1)
    assert [r["id"] for r in rapport["relocalisees"]] == [m.id]
    m2 = store.get(m.id)
    assert m2.statut == "active" and m2.source_commit == c2 and m2.source_debut == m.source_debut + 2


def test_revalidation_si_le_fichier_change_ailleurs(store, depot):
    m = fait_dsi(store, depot)
    c1 = depot.git("rev-parse", "HEAD")
    depot.ecrire(LEGACY, depot.lire(LEGACY) + "\n// fin\n")
    c2 = depot.commit("chore: commentaire en fin de fichier")
    rapport = store.invalider_depuis_git(depot.racine, c1)
    assert [r["id"] for r in rapport["revalidees"]] == [m.id]
    assert store.get(m.id).source_commit == c2


def test_suppression_et_renommage(store, depot):
    m_adr = store.ajouter("semantique", "Le montant nul est converti en 0.0 par l'adaptateur", "projet:neoflow",
                          source=f"{ADR}@HEAD:3-5", depot=depot.racine)
    m_dsi = fait_dsi(store, depot)
    c1 = depot.git("rev-parse", "HEAD")
    depot.git("mv", LEGACY, LEGACY.replace("RegleValidationLegacy", "RegleValidationHistorique"))
    depot.git("rm", "-q", ADR)
    depot.commit("refactor: renommage + suppression ADR")
    store.invalider_depuis_git(depot.racine, c1)
    assert store.get(m_adr.id).statut == "invalide" and "supprimé" in store.get(m_adr.id).motif
    assert store.get(m_dsi.id).statut == "active"
    assert store.get(m_dsi.id).source_fichier.endswith("RegleValidationHistorique.java")


def test_lecture_defensive_sans_passage_du_pipeline(store, depot):
    m = fait_dsi(store, depot)
    depot.ecrire(LEGACY, depot.lire(LEGACY).replace("departement == DSI", "DSI.equals(departement)"))
    depot.commit("fix: comparaison de chaînes")
    valides, ecartees = store.rechercher("DSI MATERIEL_IT référence", ["projet:neoflow"], depot=depot.racine)
    assert valides == [] and ecartees[0][0].id == m.id


def test_ecriture_idempotente_et_oubli(store, depot):
    m1 = fait_dsi(store, depot)
    m2 = fait_dsi(store, depot)
    assert m1.id == m2.id and len(store.lister()) == 1
    store.ajouter("episodique", "Mission Acme : préférer Gradle", "client:acme", source=f"{ADR}@HEAD",
                  depot=depot.racine)
    assert store.oublier_portee("client:acme") == 1
    assert store.oublier(m1.id) and store.lister() == []


def test_export_markdown_avec_provenance(store, depot):
    fait_dsi(store, depot)
    md = store.exporter_markdown(["projet:neoflow"])
    assert "## Faits" in md and "RegleValidationLegacy.java@" in md


def test_revalidation_globale_avant_export(store, depot):
    m = fait_dsi(store, depot)
    depot.ecrire(LEGACY, depot.lire(LEGACY).replace("departement == DSI", "DSI.equals(departement)"))
    depot.commit("fix: comparaison de chaînes")
    bilan = store.revalider(depot.racine)
    assert bilan["invalidee"] == 1 and store.get(m.id).statut == "invalide"
    assert "DSI est comparée" not in store.exporter_markdown(["projet:neoflow"])
