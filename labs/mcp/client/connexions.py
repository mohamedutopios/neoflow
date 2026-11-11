"""Connexions MCP persistantes (stdio) utilisables depuis du code SYNCHRONE.

L'agent du J4 appelle `Tool.handler(dict) -> str` de façon synchrone ; le client MCP est asynchrone.
On fait tourner une boucle asyncio dans un thread dédié : une tâche par serveur garde la session
ouverte (`async with Client(...)`), et chaque appel d'outil est soumis à cette boucle.

Choix de sécurité du client :
- environnement du serveur construit explicitement (`ServeurConfig.environnement()`) ;
- aucune capacité `roots` annoncée (un serveur comme server-filesystem garde donc SES dossiers) ;
- négociation « legacy » (révision 2025-11-25), comprise par tous les serveurs du lab.
"""
from __future__ import annotations

import asyncio
import atexit
import threading
from dataclasses import dataclass, field
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from client.config import ServeurConfig


@dataclass
class EtatServeur:
    config: ServeurConfig
    client: Client | None = None
    outils: list = field(default_factory=list)       # mcp.types.Tool découverts (tools/list)
    statut: str = "non_demarre"                       # connecte | echec | ferme
    erreur: str | None = None
    arret: asyncio.Event | None = None
    pret: threading.Event = field(default_factory=threading.Event)
    termine: threading.Event = field(default_factory=threading.Event)


class GestionnaireMCP:
    """Démarre les serveurs, garde les sessions, exécute les appels ; à fermer avec `fermer()`."""

    def __init__(self, dossier_stderr: Path | None = None) -> None:
        self.dossier_stderr = dossier_stderr          # stderr des serveurs (leurs journaux) : un fichier par serveur
        self.boucle = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.boucle.run_forever, name="mcp-client", daemon=True)
        self.thread.start()
        self.serveurs: dict[str, EtatServeur] = {}
        atexit.register(self.fermer)

    # ------------------------------------------------------------------ #
    def connecter(self, config: ServeurConfig) -> EtatServeur:
        etat = EtatServeur(config=config)
        self.serveurs[config.nom] = etat
        asyncio.run_coroutine_threadsafe(self._session(etat), self.boucle)
        if not etat.pret.wait(timeout=config.delai_s + 5):
            etat.statut, etat.erreur = "echec", f"délai de connexion dépassé ({config.delai_s} s)"
        return etat

    async def _session(self, etat: EtatServeur) -> None:
        cfg = etat.config
        log_file = None
        if self.dossier_stderr is not None:
            self.dossier_stderr.mkdir(parents=True, exist_ok=True)
            log_file = self.dossier_stderr / f"{cfg.nom}.stderr.log"
        transport = StdioTransport(command=cfg.commande[0], args=cfg.commande[1:],
                                   env=cfg.environnement(), cwd=str(cfg.racine), log_file=log_file)
        client = Client(transport, mode="legacy", timeout=cfg.delai_s, init_timeout=cfg.delai_s)
        etat.arret = asyncio.Event()
        try:
            async with client:
                etat.client = client
                etat.outils = list(await client.list_tools())
                etat.statut = "connecte"
                etat.pret.set()
                await etat.arret.wait()
        except Exception as exc:  # noqa: BLE001 - commande introuvable, serveur qui plante...
            etat.statut, etat.erreur = "echec", f"{type(exc).__name__}: {str(exc)[:200]}"
        finally:
            if etat.statut == "connecte":
                etat.statut = "ferme"
            etat.client = None
            etat.pret.set()
            etat.termine.set()

    # ------------------------------------------------------------------ #
    def appeler(self, serveur: str, outil: str, arguments: dict, delai_s: float | None = None):
        """Appel synchrone ; renvoie le CallToolResult (is_error inclus), lève TimeoutError ou RuntimeError."""
        etat = self.serveurs.get(serveur)
        if etat is None or etat.client is None:
            raise RuntimeError(f"serveur MCP '{serveur}' non connecté ({etat.erreur if etat else 'inconnu'})")
        futur = asyncio.run_coroutine_threadsafe(
            etat.client.call_tool(outil, arguments, raise_on_error=False), self.boucle)
        return futur.result(timeout=delai_s or etat.config.delai_s)

    def fermer(self) -> None:
        for etat in self.serveurs.values():
            if etat.arret is not None and not self.boucle.is_closed():
                self.boucle.call_soon_threadsafe(etat.arret.set)
        for etat in self.serveurs.values():
            if etat.arret is not None:
                etat.termine.wait(timeout=5)      # le processus serveur est arrêté proprement
        if self.boucle.is_running():
            self.boucle.call_soon_threadsafe(self.boucle.stop)
            self.thread.join(timeout=5)
