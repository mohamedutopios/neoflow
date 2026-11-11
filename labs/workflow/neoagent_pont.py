"""Pont vers l'agent `neoagent` du J4 (labs/agent), utilisé par l'action `deleguer_neoagent`.

Contrat (contrat neoagent), vérifié sur labs/agent : `Politique.lecture(racine)` (garde_fous),
`Approbateur(mode="refus")`, `Journal(path)`, `Resultat(statut, reponse, etapes, usage, session, appels_outils)`.
Contrat attendu :
  from neoagent.tools import Tool, outils_de_base     # outils_de_base(repo, politique) -> list[Tool]
  from neoagent.agent import Agent                    # Agent(tools, modele, max_etapes, budget_tokens,
                                                      #       approbateur, journal, offline).executer(tache)
Import tolérant : labs/agent est écrit en parallèle. Les classes annexes (Politique, Approbateur, Journal)
sont cherchées dans les modules du paquet et passées seulement si le constructeur les attend.

Garde-fou propre au J9 : l'agent délégué ne reçoit QUE les outils de risque « lecture ». La délégation
elle-même est une action sensible : elle passe par l'approbation humaine du workflow.
"""
from __future__ import annotations

import dataclasses
import importlib
import inspect
import sys
from pathlib import Path
from typing import Any

ICI = Path(__file__).resolve().parent


class NeoagentIndisponible(RuntimeError):
    """labs/agent absent, non importable ou d'une API inattendue."""


def _chercher(nom: str, modules: list[Any]) -> Any | None:
    return next((getattr(m, nom) for m in modules if m is not None and hasattr(m, nom)), None)


def _importer(module: str) -> Any | None:
    try:
        return importlib.import_module(module)
    except ImportError:
        return None


def charger(cfg: dict):
    chemin = (ICI / cfg["neoagent"]["chemin_lab"]).resolve()
    if not (chemin / "neoagent").is_dir():
        raise NeoagentIndisponible(f"labs/agent absent ({chemin}/neoagent introuvable)")
    if str(chemin) not in sys.path:
        sys.path.insert(0, str(chemin))
    try:
        agent_mod = importlib.import_module("neoagent.agent")
        tools_mod = importlib.import_module("neoagent.tools")
    except Exception as exc:  # dépendances manquantes, erreur de syntaxe en cours d'écriture...
        raise NeoagentIndisponible(f"neoagent non importable : {type(exc).__name__}: {exc}") from exc
    annexes = [agent_mod, tools_mod] + [_importer(f"neoagent.{m}")
                                        for m in ("garde_fous", "politique", "approbation", "journal")]
    return agent_mod, tools_mod, annexes


def _construire(cls, **valeurs):
    """Instancie `cls` en ne passant que les paramètres qu'il accepte ; None si impossible."""
    if cls is None:
        return None
    try:
        params = inspect.signature(cls).parameters
        return cls(**{k: v for k, v in valeurs.items() if k in params})
    except Exception:
        return None


def _vers_dict(resultat: Any) -> dict:
    if dataclasses.is_dataclass(resultat):
        brut = dataclasses.asdict(resultat)
    elif isinstance(resultat, dict):
        brut = dict(resultat)
    else:
        brut = {k: getattr(resultat, k) for k in dir(resultat) if not k.startswith("_")
                and not callable(getattr(resultat, k))}
    reponse = next((brut[k] for k in ("reponse_finale", "reponse", "reponse_texte", "texte") if k in brut), "")
    etapes = brut.get("etapes")
    return {"statut": str(brut.get("statut", "inconnu")), "reponse": str(reponse)[:4000],
            "etapes": len(etapes) if isinstance(etapes, list) else etapes, "usage": brut.get("usage")}


def deleguer(tache: str, depot: Path, cfg: dict, *, offline: bool, journal: Path) -> dict:
    """Exécute `tache` avec neoagent, outils en lecture seule. Lève NeoagentIndisponible si absent."""
    agent_mod, tools_mod, annexes = charger(cfg)
    Agent, outils_de_base = getattr(agent_mod, "Agent", None), getattr(tools_mod, "outils_de_base", None)
    if Agent is None or outils_de_base is None:
        raise NeoagentIndisponible("API neoagent inattendue : Agent ou outils_de_base introuvable")
    Politique = _chercher("Politique", annexes)
    if Politique is not None and callable(getattr(Politique, "lecture", None)):
        politique = Politique.lecture(depot)          # préréglage J4 : aucune écriture, Git en lecture seule
    else:
        politique = _construire(Politique, repo=depot, racine=depot, lecture_seule=True)
    try:
        outils = outils_de_base(depot, politique)
    except TypeError:
        outils = outils_de_base(repo=depot, politique=politique)
    lecture = [t for t in outils if getattr(t, "risque", "lecture") == "lecture"]
    n = cfg["neoagent"]
    kwargs = {"modele": n["modele"], "max_etapes": n["max_etapes"], "budget_tokens": n["budget_tokens"],
              "offline": offline}
    approbateur = _construire(_chercher("Approbateur", annexes), mode="refus")  # refuse écriture et exécution
    journal_obj = _construire(_chercher("Journal", annexes), path=journal, chemin=journal)
    params = inspect.signature(Agent).parameters
    if approbateur is not None and "approbateur" in params:
        kwargs["approbateur"] = approbateur
    if journal_obj is not None and "journal" in params:
        kwargs["journal"] = journal_obj
    agent = Agent(lecture, **{k: v for k, v in kwargs.items() if k in params})
    try:
        resultat = agent.executer(tache)
    except NotImplementedError as exc:   # socle du J4 : la boucle est un TODO tant que le TP n'est pas fait
        raise NeoagentIndisponible(f"neoagent incomplet (TODO du J4) : {str(exc)[:120]}") from exc
    return {**_vers_dict(resultat), "outils": [getattr(t, "name", "?") for t in lecture]}
