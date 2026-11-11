"""Validation STRUCTURELLE du flow Kestra (sans instance Kestra) : YAML, ids, types, références.

Ne remplace pas `kestra flow validate` ni l'éditeur Kestra, qui connaissent le schéma exact
des plugins installés. Vérifie ce qui casse le plus souvent : ids dupliqués, types mal
orthographiés, références à des tâches/variables/entrées inexistantes, sous-commandes inconnues.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

FLOW = Path(__file__).resolve().parents[1] / "kestra" / "reindex-incremental.yml"

# Types utilisés, tels que documentés par Kestra (core, plugin-git, plugin-script-python, runner docker).
TYPES_CONNUS = {
    "io.kestra.plugin.core.flow.If",
    "io.kestra.plugin.core.flow.WorkingDirectory",
    "io.kestra.plugin.core.log.Log",
    "io.kestra.plugin.core.kv.Set",
    "io.kestra.plugin.core.trigger.Webhook",
    "io.kestra.plugin.git.Clone",
    "io.kestra.plugin.scripts.python.Commands",
    "io.kestra.plugin.scripts.runner.docker.Docker",
}
ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


@pytest.fixture(scope="module")
def flow() -> dict:
    return yaml.safe_load(FLOW.read_text(encoding="utf-8"))


def taches(liste):
    for t in liste or []:
        yield t
        for cle in ("tasks", "then", "else", "errors", "finally"):
            yield from taches(t.get(cle))


def toutes(flow):
    return list(taches(flow["tasks"])) + list(taches(flow.get("errors")))


def chaines(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from chaines(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from chaines(v)


def test_entete(flow):
    assert flow["id"] == "reindex-incremental" and ID_RE.match(flow["id"])
    assert re.fullmatch(r"[a-z0-9_.-]+", flow["namespace"])
    assert flow["concurrency"] == {"limit": 1, "behavior": "QUEUE"}


def test_ids_uniques_et_types_connus(flow):
    ts = toutes(flow)
    ids = [t["id"] for t in ts]
    assert len(ids) == len(set(ids)), "ids de tâches dupliqués"
    for t in ts:
        assert ID_RE.match(t["id"]), t["id"]
        assert t["type"] in TYPES_CONNUS, t["type"]
        if "taskRunner" in t:
            assert t["taskRunner"]["type"] in TYPES_CONNUS
    for trig in flow["triggers"]:
        assert trig["type"] in TYPES_CONNUS


def test_webhook_et_cle(flow):
    (trig,) = flow["triggers"]
    assert trig["type"].endswith("trigger.Webhook") and len(trig["key"]) >= 24


def test_retries_bornes_et_timeouts(flow):
    for t in toutes(flow):
        if t["type"].endswith("python.Commands"):
            assert re.fullmatch(r"PT\d+[MS]", t["timeout"])
        if "retry" in t:
            r = t["retry"]
            assert r["type"] in ("constant", "exponential", "random")
            assert 1 <= r["maxAttempts"] <= 5


def test_references_pebble_resolues(flow):
    ids = {t["id"] for t in toutes(flow)}
    variables, entrees = set(flow["variables"]), {i["id"] for i in flow["inputs"]}
    for s in chaines(flow):
        assert s.count("{{") == s.count("}}"), s
        for m in re.findall(r"outputs\.(\w+)\.", s):
            assert m in ids, f"sortie d'une tâche inconnue : {m}"
        for m in re.findall(r"(?<![\w.])vars\.(\w+)", s):
            assert m in variables, f"variable inconnue : {m}"
        for m in re.findall(r"(?<![\w.])inputs\.(\w+)", s):
            assert m in entrees, f"entrée inconnue : {m}"


def test_sous_commandes_du_script_existent(flow):
    import reindex_incremental

    source = Path(reindex_incremental.__file__).read_text(encoding="utf-8")
    sous_commandes = set(re.findall(r'sp\.add_parser\("(\w+)"\)', source)) | {"appliquer", "valider"}
    for t in toutes(flow):
        for cmd in t.get("commands", []):
            if "reindex_incremental.py" in cmd:
                sc = re.search(r"\}\}\s*(\w+)\s+--plan|--kestra\s+(\w+)\s", cmd)
                nom = next(g for g in sc.groups() if g)
                assert nom in sous_commandes, nom


def test_kv_avance_seulement_apres_validation(flow):
    (bloc,) = [t for t in toutes(flow) if t["id"] == "espace_travail"]
    ordre = [t["id"] for t in bloc["tasks"]]
    assert ordre.index("si_changements") < ordre.index("memoriser_commit")
    (si,) = [t for t in toutes(flow) if t["id"] == "si_changements"]
    assert [t["id"] for t in si["then"]] == ["indexer", "valider"]
