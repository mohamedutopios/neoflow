"""Réindexation incrémentale : delta Git, filtrage, idempotence, validation, invalidation mémoire."""
from __future__ import annotations

import json
import sys

import pytest

import reindex_incremental as ri
from config import charger
from memoire import StoreMemoire

CIRCUIT = "backend/src/main/java/com/neosoft/neoflow/validation/CircuitValidationService.java"
LEGACY = "backend/src/main/java/com/neosoft/neoflow/legacy/RegleValidationLegacy.java"
ADR = "docs/adr/ADR-001-circuit-validation.md"
UTILS = "frontend/src/legacy/utils-legacy.js"


def run(depot, etat, *args) -> int:
    return ri.main(["--depot", str(depot.racine), "--etat", str(etat), "--simulation", *args])


def index(etat) -> dict:
    return json.loads((etat / "index_simule.json").read_text())


def dernier(etat) -> str | None:
    return ri.lire_json(etat / "index_state.json", {}).get("dernier_commit_indexe")


def test_premier_passage_complet_filtre_les_dependances(depot, etat):
    plan = ri.planifier(depot.racine, charger(), etat, None)
    assert plan["mode"] == "complet"
    chemins = {f["path"] for f in plan["a_indexer"]}
    assert {CIRCUIT, LEGACY, ADR, UTILS} <= chemins
    assert "frontend/node_modules/lib/index.js" in {i["path"] for i in plan["ignores"]}
    assert run(depot, etat, "tout") == 0
    assert dernier(etat) == depot.git("rev-parse", "HEAD")


def test_passage_incremental_ne_touche_que_le_delta(depot, etat):
    run(depot, etat, "tout")
    depot.ecrire(CIRCUIT, depot.lire(CIRCUIT).replace("0.0", "0d"))                      # M
    depot.ecrire("docs/adr/ADR-002-montant.md", "# ADR-002\nMontant nul = 0.\n")            # A
    depot.git("rm", "-q", UTILS)                                                            # D
    depot.git("mv", LEGACY, LEGACY.replace("Legacy.java", "Historique.java"))               # R
    depot.ecrire("README.txt", "hors motifs\n")                                             # ignoré
    cible = depot.commit("feat: delta varié")

    plan = ri.planifier(depot.racine, charger(), etat, None)
    assert plan["mode"] == "incremental"
    assert {f["path"] for f in plan["a_indexer"]} == {CIRCUIT, "docs/adr/ADR-002-montant.md",
                                                       LEGACY.replace("Legacy.java", "Historique.java")}
    assert set(plan["a_supprimer"]) == {UTILS, LEGACY}
    assert [i["path"] for i in plan["ignores"]] == ["README.txt"]

    assert run(depot, etat, "tout") == 0
    idx = index(etat)
    assert UTILS not in idx and LEGACY not in idx
    assert idx[CIRCUIT]["commit"] == cible and idx[ADR]["commit"] != cible   # ADR-001 non réindexé
    assert dernier(etat) == cible


def test_relance_sur_la_meme_cible_est_un_no_op(depot, etat):
    run(depot, etat, "tout")
    avant = index(etat)
    assert run(depot, etat, "tout") == 0
    assert ri.planifier(depot.racine, charger(), etat, None)["mode"] == "a_jour"
    assert index(etat) == avant


def test_validation_en_echec_ne_fait_pas_avancer_le_pointeur(depot, etat, tmp_path):
    run(depot, etat, "tout")
    c1 = dernier(etat)
    depot.ecrire(CIRCUIT, depot.lire(CIRCUIT) + "\n// modif\n")
    depot.commit("chore: modif")
    plan_f = tmp_path / "plan.json"
    assert run(depot, etat, "plan", "--sortie", str(plan_f)) == 0
    assert run(depot, etat, "appliquer", "--plan", str(plan_f)) == 0
    idx = index(etat)
    idx[CIRCUIT]["commit"] = c1                          # index corrompu / indexeur défaillant
    (etat / "index_simule.json").write_text(json.dumps(idx))
    assert run(depot, etat, "valider", "--plan", str(plan_f)) == 2
    assert dernier(etat) == c1                           # le prochain passage reprendra ce delta


def test_reindexation_invalide_les_memoires_touchees(depot, etat):
    run(depot, etat, "tout")
    store = StoreMemoire(etat / "memoire.db", charger())
    m = store.ajouter("semantique", "Le montant nul est converti en 0.0 par CircuitValidationService",
                      "projet:neoflow", source=f"{CIRCUIT}@HEAD:12-12", depot=depot.racine)
    depot.ecrire(CIRCUIT, depot.lire(CIRCUIT).replace(": 0.0;", ": BigDecimal.ZERO.doubleValue();"))
    depot.commit("refactor: montant nul")
    plan = ri.planifier(depot.racine, charger(), etat, None)
    rapport = ri.appliquer(depot.racine, charger(), etat, plan, simulation=True)
    assert [r["id"] for r in rapport["memoire"]["invalidees"]] == [m.id]


def test_sorties_au_format_kestra(depot, etat, tmp_path, capsys):
    assert ri.main(["--depot", str(depot.racine), "--etat", str(etat), "--kestra", "plan",
                    "--sortie", str(tmp_path / "plan.json")]) == 0
    ligne = [l for l in capsys.readouterr().out.splitlines() if l.startswith("::")][0]
    assert ligne.endswith("::") and " " not in ligne
    sorties = json.loads(ligne[2:-2])["outputs"]
    assert sorties["mode"] == "complet" and sorties["nb_a_indexer"] >= 4


def test_push_de_creation_de_branche(depot, etat):
    assert ri.planifier(depot.racine, charger(), etat, "0" * 40)["mode"] == "complet"


def test_verrou_empeche_deux_passages_simultanes(depot, etat):
    (etat / "reindex.lock").write_text("1234 en cours")
    with pytest.raises(SystemExit) as exc:
        run(depot, etat, "tout")
    assert exc.value.code == 3


# ---------------------------------------------------------------- contrat du lab RAG J05 (factice)
FAUX_RAG_COMMON = '''
import hashlib, json, os, subprocess
from pathlib import Path
from types import SimpleNamespace

def load_config(config_path=None):
    return {"_repo_root": os.environ["NEOFLOW_REPO_ROOT"], "_storage_dir": os.environ["NEOFLOW_RAG_HOME"]}

def sha256_text(texte):
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()

def select_corpus(cfg):
    out = subprocess.run(["git", "-C", cfg["_repo_root"], "ls-files"], capture_output=True, text=True).stdout
    return SimpleNamespace(files=[f for f in out.split() if f.endswith((".java", ".md"))])

def read_manifest(cfg):
    p = Path(cfg["_storage_dir"]) / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else None
'''
FAUX_INDEXER = '''
import json, subprocess
from pathlib import Path
from rag_common import select_corpus, sha256_text

def run_index(cfg, incremental=False, dry_run=False, quiet=False):
    root = Path(cfg["_repo_root"])
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    files = {f: {"sha256": sha256_text((root / f).read_text())} for f in select_corpus(cfg).files}
    manifeste = {"git": {"commit": head[:7], "commit_full": head}, "files": files, "chunks": len(files)}
    Path(cfg["_storage_dir"]).mkdir(parents=True, exist_ok=True)
    (Path(cfg["_storage_dir"]) / "manifest.json").write_text(json.dumps(manifeste))
    return manifeste
'''


@pytest.fixture
def faux_lab_rag(tmp_path, depot, monkeypatch):
    lab = tmp_path / "rag"
    lab.mkdir()
    (lab / "rag_common.py").write_text(FAUX_RAG_COMMON)
    (lab / "indexer.py").write_text(FAUX_INDEXER)
    monkeypatch.setenv("NEOFLOW_REPO_ROOT", str(depot.racine))
    monkeypatch.setenv("NEOFLOW_RAG_HOME", str(tmp_path / "rag_index"))
    for m in ("indexer", "rag_common"):
        monkeypatch.delitem(sys.modules, m, raising=False)
    cfg = charger()
    cfg["rag"].update({"activer": "auto", "chemin_lab": str(lab)})
    yield cfg
    for m in ("indexer", "rag_common"):
        sys.modules.pop(m, None)
    while str(lab) in sys.path:
        sys.path.remove(str(lab))


def test_adaptateur_lab_rag_j05_run_index_et_manifeste(depot, etat, faux_lab_rag):
    cfg = faux_lab_rag
    index, raison = ri.choisir_index(cfg, etat, depot.racine, simulation=False)
    assert isinstance(index, ri.IndexLabRagJ05), raison
    plan = ri.planifier(depot.racine, cfg, etat, None)
    ri.appliquer(depot.racine, cfg, etat, plan, simulation=False)
    rapport = ri.valider(depot.racine, cfg, etat, plan, simulation=False)
    assert rapport["statut"] == "ok" and rapport["infos"]          # .js et node_modules hors corpus J05

    depot.ecrire(CIRCUIT, depot.lire(CIRCUIT) + "\n// modif\n")
    depot.commit("chore: modif")
    plan = ri.planifier(depot.racine, cfg, etat, None)
    assert ri.valider(depot.racine, cfg, etat, plan, simulation=False)["statut"] == "echec"   # pas réindexé
    ri.appliquer(depot.racine, cfg, etat, plan, simulation=False)
    assert ri.valider(depot.racine, cfg, etat, plan, simulation=False)["statut"] == "ok"


def test_lab_rag_sur_un_autre_depot_degrade_en_simulation(depot, etat, faux_lab_rag, monkeypatch, tmp_path):
    monkeypatch.setenv("NEOFLOW_REPO_ROOT", str(tmp_path / "autre"))
    index, raison = ri.choisir_index(faux_lab_rag, etat, depot.racine, simulation=False)
    assert isinstance(index, ri.IndexSimule) and "NEOFLOW_REPO_ROOT" in raison
