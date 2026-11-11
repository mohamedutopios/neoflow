"""Points d'extension du lab : les composants codés en TP se branchent ici, sans modifier le lab.

Dans un fichier de configuration (passé par --config) :

  extensions:
    politique_memoire: extensions/tp1_memoire.py:valider_ecriture
    verdict_souvenir:  extensions/tp1_memoire.py:verdict_souvenir
    routeur:           extensions/tp2_routage.py:router
    source_suivante:   extensions/tp2_routage.py:source_suivante
    noeuds:            extensions/tp3_noeuds.py          # module : approbation, executer_action, apres_verification
    classer_changements: extensions/tp4_reindex.py:classer_changements

Les chemins relatifs sont résolus depuis le dossier du fichier de configuration. Une valeur `null`
(défaut) garde l'implémentation de référence du lab.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

_CACHE: dict[str, ModuleType] = {}


def _module(cible: str, base: Path) -> ModuleType:
    if cible.endswith(".py") or "/" in cible:
        chemin = (base / cible).resolve() if not Path(cible).is_absolute() else Path(cible)
        if not chemin.is_file():
            raise FileNotFoundError(f"extension introuvable : {chemin}")
        cle = str(chemin)
        if cle not in _CACHE:
            nom = f"ext_{chemin.stem}_{abs(hash(cle)) % 10**8}"
            spec = importlib.util.spec_from_file_location(nom, chemin)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[nom] = mod
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            _CACHE[cle] = mod
        return _CACHE[cle]
    return importlib.import_module(cible)


def module(cfg: dict, nom: str) -> ModuleType | None:
    spec = (cfg.get("extensions") or {}).get(nom)
    return _module(spec, Path(cfg.get("_base", "."))) if spec else None


def fonction(cfg: dict, nom: str, defaut: Callable[..., Any]) -> Callable[..., Any]:
    """Fonction d'extension `chemin.py:fonction` ou `paquet.module:fonction`, sinon `defaut`."""
    spec = (cfg.get("extensions") or {}).get(nom)
    if not spec:
        return defaut
    cible, _, attr = spec.rpartition(":")
    if not cible:
        raise ValueError(f"extensions.{nom} : format attendu 'fichier.py:fonction', reçu {spec!r}")
    fn = getattr(_module(cible, Path(cfg.get("_base", "."))), attr, None)
    if not callable(fn):
        raise AttributeError(f"extensions.{nom} : {attr!r} absent de {cible}")
    return fn
