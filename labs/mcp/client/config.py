"""Lecture de `configs/mcp_client.json` : serveurs, environnement transmis, outils autorisés et leur risque.

La configuration est la POLITIQUE : un outil absent de `outils` n'est jamais exposé à l'agent, et son
risque (`lecture`, `ecriture`, `execution`) est décidé ici, pas par les annotations du serveur.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parents[1]                     # labs/mcp
CONFIG_PAR_DEFAUT = LAB_DIR / "configs" / "mcp_client.json"
RISQUES = ("lecture", "ecriture", "execution")
VARIABLE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


class ConfigInvalide(ValueError):
    """Configuration MCP incohérente : refusée au chargement, pas à l'exécution."""


@dataclass(frozen=True)
class RegleOutil:
    risque: str = "lecture"
    confirmation: bool = False                 # demander l'accord humain avant chaque appel
    parametre_confirmation: str | None = None  # argument serveur posé par le CLIENT après accord (jamais par le modèle)


@dataclass
class ServeurConfig:
    nom: str
    commande: list[str]
    racine: Path
    env: dict[str, str] = field(default_factory=dict)
    env_hote: list[str] = field(default_factory=list)
    outils: dict[str, RegleOutil] = field(default_factory=dict)
    actif: bool = True
    delai_s: float = 30.0

    def environnement(self) -> dict[str, str]:
        """Environnement EXPLICITE du processus serveur : variables de l'hôte listées + valeurs déclarées.

        Le SDK `mcp` n'hérite par défaut que d'une liste blanche (PATH, HOME, USER...) ; on ajoute ici
        seulement ce que la config nomme. OpenCode 1.19, lui, transmet tout son environnement.
        """
        env = {k: os.environ[k] for k in self.env_hote if k in os.environ}
        for cle, valeur in self.env.items():
            env[cle] = VARIABLE.sub(lambda m: os.environ.get(m.group(1), ""), valeur)
        return env


def _regle(nom: str, brut: dict | str) -> RegleOutil:
    if isinstance(brut, str):
        brut = {"risque": brut}
    risque = brut.get("risque", "lecture")
    if risque not in RISQUES:
        raise ConfigInvalide(f"{nom} : risque '{risque}' inconnu (attendus : {', '.join(RISQUES)}).")
    # Toute écriture ou exécution exige une confirmation humaine : impossible de la désactiver.
    confirmation = bool(brut.get("confirmation", risque != "lecture")) or risque != "lecture"
    return RegleOutil(risque=risque, confirmation=confirmation,
                      parametre_confirmation=brut.get("parametre_confirmation"))


def charger_config(chemin: str | os.PathLike | None = None) -> tuple[list[ServeurConfig], dict]:
    chemin = Path(chemin or os.environ.get("NEOFLOW_MCP_CLIENT_CONFIG") or CONFIG_PAR_DEFAUT).resolve()
    brut = json.loads(chemin.read_text(encoding="utf-8"))
    racine = (chemin.parent / brut.get("racine", ".")).resolve()
    serveurs = []
    for nom, s in brut.get("serveurs", {}).items():
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,30}", nom):
            raise ConfigInvalide(f"Nom de serveur invalide : '{nom}'.")
        if not s.get("commande"):
            raise ConfigInvalide(f"{nom} : 'commande' obligatoire (liste, sans shell).")
        serveurs.append(ServeurConfig(
            nom=nom, commande=list(s["commande"]), racine=(racine / s.get("cwd", ".")).resolve(),
            env=dict(s.get("env", {})), env_hote=list(s.get("env_hote", ["PATH", "HOME"])),
            outils={o: _regle(f"{nom}.{o}", r) for o, r in s.get("outils", {}).items()},
            actif=bool(s.get("actif", True)), delai_s=float(s.get("delai_s", 30)),
        ))
    options = {"racine": racine, "journal": brut.get("journal"), "source": chemin}
    return serveurs, options
