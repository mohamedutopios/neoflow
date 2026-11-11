"""Points d'extension (composants codés en TP) et délégation à neoagent (J4), avec un faux paquet au contrat neoagent."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from langgraph.types import Command

import extensions
import workflow as wf
from config import charger
from memoire import MemoireRefusee, StoreMemoire

from conftest import LAB

Q = "Où est calculé le niveau de validation dans CircuitValidationService ?"
CIRCUIT = "backend/src/main/java/com/neosoft/neoflow/validation/CircuitValidationService.java"

FAUX_TOOLS = '''
from dataclasses import dataclass
from typing import Callable, Literal

@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], str]
    risque: Literal["lecture", "ecriture", "execution"] = "lecture"

class Politique:
    def __init__(self, racine=None, lecture_seule=False):
        self.racine, self.lecture_seule = racine, lecture_seule

    @classmethod
    def lecture(cls, racine):
        return cls(racine=racine, lecture_seule=True)

def outils_de_base(repo, politique):
    rien = lambda e: ""
    return [Tool("lire_fichier", "lit", {}, rien), Tool("chercher", "cherche", {}, rien),
            Tool("editer_fichier", "édite", {}, rien, "ecriture"),
            Tool("executer_commande", "exécute", {}, rien, "execution")]
'''
FAUX_AGENT = '''
import json, os
from dataclasses import dataclass, field

@dataclass
class Resultat:
    statut: str
    reponse_finale: str
    etapes: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)

class Journal:
    def __init__(self, path):
        self.path = path

class Agent:
    def __init__(self, tools, modele="claude-sonnet-5-5", max_etapes=30, budget_tokens=200_000,
                 approbateur=None, journal=None, offline=False):
        self.tools, self.offline = tools, offline

    def executer(self, tache):
        with open(os.environ["FAUX_NEOAGENT_TRACE"], "a") as f:
            f.write(json.dumps({"outils": [t.name for t in self.tools], "offline": self.offline}) + "\\n")
        return Resultat("termine", "Rapport : le niveau est calculé par CircuitValidationService.java:30-33",
                        etapes=[1, 2], usage={"input_tokens": 0, "output_tokens": 0})
'''


@pytest.fixture
def faux_neoagent(tmp_path, monkeypatch):
    lab = tmp_path / "agent"
    (lab / "neoagent").mkdir(parents=True)
    (lab / "neoagent" / "__init__.py").write_text("")
    (lab / "neoagent" / "tools.py").write_text(FAUX_TOOLS)
    (lab / "neoagent" / "agent.py").write_text(FAUX_AGENT)
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setenv("FAUX_NEOAGENT_TRACE", str(trace))
    for m in [m for m in sys.modules if m == "neoagent" or m.startswith("neoagent.")]:
        monkeypatch.delitem(sys.modules, m)
    yield lab, trace
    for m in [m for m in sys.modules if m == "neoagent" or m.startswith("neoagent.")]:
        sys.modules.pop(m, None)
    while str(lab) in sys.path:
        sys.path.remove(str(lab))


def cfg_test(**neoagent) -> dict:
    cfg = charger()
    cfg["retries"].update({"intervalle_initial_s": 0.01, "jitter": False})
    cfg["rag"]["activer"] = "non"
    cfg["neoagent"].update(neoagent)
    return cfg


def session(depot, etat, cfg, **kw):
    return wf.ouvrir_session(offline=True, etat=str(etat), depot=str(depot.racine), cfg=cfg, **kw)


# ---------------------------------------------------------------- extensions
def test_extension_par_chemin_relatif_au_fichier_de_config(tmp_path):
    (tmp_path / "ext").mkdir()
    (tmp_path / "ext" / "mon_routeur.py").write_text(
        "def router(q):\n    return ('git', 'toujours git') if 'git' in q else (None, 'ambigu')\n")
    (tmp_path / "cfg.yaml").write_text("extensions:\n  routeur: ext/mon_routeur.py:router\n")
    cfg = charger(tmp_path / "cfg.yaml")
    fn = extensions.fonction(cfg, "routeur", lambda q: ("symboles", "défaut"))
    assert fn("historique git") == ("git", "toujours git")
    assert extensions.fonction(charger(), "routeur", print) is print          # null : référence du lab


def test_politique_memoire_branchee(depot, etat):
    def tout_refuser(type, contenu, portee, source):
        raise MemoireRefusee("politique du TP : rien n'est mémorisé")
    store = StoreMemoire(etat / "m.db", charger(), politique=tout_refuser)
    with pytest.raises(MemoireRefusee, match="TP"):
        store.ajouter("episodique", "x", "projet:neoflow")


def test_noeuds_branches_remplacent_ceux_du_lab(depot, etat, tmp_path):
    (tmp_path / "noeuds.py").write_text('''
def approbation(etat, config, ctx):
    return {"approbation": {"decision": "refuser", "motif": "nœud du TP", "approbateur": None}}
''')
    cfg = cfg_test()
    cfg["extensions"]["noeuds"] = str(tmp_path / "noeuds.py")
    s = session(depot, etat, cfg)
    s.invoquer({"question": Q, "ticket": "NF-402", "demandeur": "alice", "portee": "projet:neoflow"}, "t1")
    v = s.instantane("t1").values
    assert v["statut"] == "refuse" and v["approbation"]["motif"] == "nœud du TP"   # pas d'interrupt : nœud remplacé


# ---------------------------------------------------------------- neoagent
def lancer_delegation(s):
    s.invoquer({"question": Q, "ticket": None, "demandeur": "alice", "portee": "projet:neoflow",
                "action_demandee": "deleguer_neoagent"}, "d1")


def test_delegation_neoagent_soumise_a_approbation_et_en_lecture_seule(depot, etat, faux_neoagent):
    lab, trace = faux_neoagent
    s = session(depot, etat, cfg_test(chemin_lab=str(lab)))
    lancer_delegation(s)
    attente = s.en_attente("d1")
    assert attente["action"]["type"] == "deleguer_neoagent" and not trace.exists()   # rien lancé sans accord
    s.invoquer(Command(resume={"decision": "approuver", "approbateur": "bob"}), "d1")
    res = s.instantane("d1").values["resultat_action"]
    assert res["statut"] == "applique" and "CircuitValidationService" in res["reponse"]
    appel = json.loads(trace.read_text().splitlines()[0])
    assert appel["outils"] == ["lire_fichier", "chercher"] and appel["offline"] is True


def test_delegation_rejouee_apres_crash_sans_second_appel(depot, etat, faux_neoagent):
    lab, trace = faux_neoagent
    cfgf = etat.parent / "neo.yaml"
    cfgf.write_text(f"neoagent:\n  chemin_lab: {lab}\nrag:\n  activer: non\n")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "NEOFLOW_RAG": "off"}
    env.pop("ANTHROPIC_API_KEY", None)

    def cli(*args, rc):
        p = subprocess.run([sys.executable, str(LAB / "workflow.py"), *args, "--offline", "--etat", str(etat),
                            "--depot", str(depot.racine), "--config", str(cfgf)], capture_output=True, text=True,
                           env=env, timeout=120)
        assert p.returncode == rc, p.stdout + p.stderr
        return p.stdout

    cli("lancer", "--thread", "d1", "--demandeur", "alice", "--question", Q, "--action", "deleguer_neoagent", rc=0)
    cli("approuver", "--thread", "d1", "--approbateur", "bob", "--crash-apres-effet", rc=137)
    cli("reprendre", "--thread", "d1", rc=0)
    assert len(trace.read_text().splitlines()) == 1          # l'agent n'a tourné qu'une fois


def test_neoagent_absent_escalade_sans_effet(depot, etat, tmp_path):
    s = session(depot, etat, cfg_test(chemin_lab=str(tmp_path / "inexistant")))
    lancer_delegation(s)
    s.invoquer(Command(resume={"decision": "approuver", "approbateur": "bob"}), "d1")
    v = s.instantane("d1").values
    assert v["statut"] == "escalade" and v["resultat_action"]["statut"] == "indisponible"


AGENT_SOCLE = Path(__file__).resolve().parents[2] / "agent"
AGENT_CORRIGE = Path(os.environ.get("NEOAGENT_CORRIGE", Path(__file__).resolve().parents[5]
                                    / "J04_agent_dev_patterns" / "solutions" / "labs" / "agent"))


def test_neoagent_du_socle_incomplet_escalade_proprement(depot, etat):
    """Dans le socle, la boucle de neoagent est un TODO du J4 : la délégation doit échouer sans effet."""
    if not (AGENT_SOCLE / "neoagent" / "agent.py").is_file():
        pytest.skip("labs/agent absent")
    s = session(depot, etat, cfg_test(chemin_lab=str(AGENT_SOCLE)))
    lancer_delegation(s)
    s.invoquer(Command(resume={"decision": "approuver", "approbateur": "bob"}), "d1")
    v = s.instantane("d1").values
    assert (v["statut"], v["resultat_action"]["statut"]) in {("escalade", "indisponible"),   # TODO du J4 restants
                                                             ("termine", "applique")}       # J4 déjà terminé


@pytest.mark.skipif(not (AGENT_CORRIGE / "neoagent" / "agent.py").is_file(), reason="corrigé J04 absent")
def test_delegation_avec_le_vrai_neoagent_en_offline(depot, etat, monkeypatch):
    """Contrat réel du J4 (corrigé) : Politique.lecture, Approbateur(mode="refus"), Agent(..., offline=True)."""
    AGENT_REEL = AGENT_CORRIGE
    for m in [m for m in sys.modules if m == "neoagent" or m.startswith("neoagent.")]:
        monkeypatch.delitem(sys.modules, m)
    try:
        import importlib
        sys.path.insert(0, str(AGENT_REEL))
        importlib.import_module("neoagent.agent")
    except Exception as exc:  # dépendances du lab agent absentes de cet environnement
        pytest.skip(f"neoagent non importable ici : {exc}")
    s = session(depot, etat, cfg_test(chemin_lab=str(AGENT_REEL)))
    lancer_delegation(s)
    s.invoquer(Command(resume={"decision": "approuver", "approbateur": "bob"}), "d1")
    res = s.instantane("d1").values["resultat_action"]
    assert res["statut"] == "applique", res
    assert res["outils"] and not {"editer_fichier", "executer_commande"} & set(res["outils"])
