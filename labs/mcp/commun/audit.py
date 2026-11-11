"""Journal d'accès MCP au format JSONL (une ligne JSON par événement).

Branché comme middleware FastMCP : chaque découverte (tools/list) et chaque appel
(tools/call) est journalisé, y compris les refus et les erreurs de validation.

Champs : ts, trace_id, server, actor, client, event, tool, args (masqués), decision
(allowed | refused | error), reason, duration_ms, result_sha256, result_bytes, sources.

Variables d'environnement :
  NEOFLOW_MCP_AUDIT   chemin du journal (défaut : labs/mcp/var/audit.jsonl)
  NEOFLOW_MCP_ACTOR   identité technique déclarée par la config (jamais fournie par le modèle)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.exceptions import ValidationError as FastMCPValidationError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from pydantic import ValidationError as PydanticValidationError

from commun.depot import LAB_DIR
from commun.garde_fous import secrets_detectes

JOURNAL_PAR_DEFAUT = LAB_DIR / "var" / "audit.jsonl"
_verrou = threading.Lock()


class Refus(ToolError):
    """Refus volontaire décidé par la politique du serveur (distinct d'une panne).

    Le message est renvoyé au modèle (isError=true) : il doit être clair et actionnable.
    """

    def __init__(self, code: str, message: str):
        super().__init__(f"REFUS [{code}] {message}")
        self.code = code


def chemin_journal() -> Path:
    return Path(os.environ.get("NEOFLOW_MCP_AUDIT") or JOURNAL_PAR_DEFAUT)


def acteur() -> str:
    return os.environ.get("NEOFLOW_MCP_ACTOR", "acteur-non-declare")


def ecrire(evenement: dict[str, Any]) -> None:
    ligne = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **evenement}
    chemin = chemin_journal()
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with _verrou, open(chemin, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(ligne, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:  # le journal ne doit jamais faire tomber le serveur
        print(f"[audit] écriture impossible ({exc}) : {ligne}", file=sys.stderr)


def masquer_arguments(args: dict[str, Any]) -> dict[str, Any]:
    """Arguments journalisables : secrets masqués, textes longs remplacés par une empreinte.

    TODO T1.4 (TP 1) — Pour chaque valeur :
      - chaîne contenant un secret (secrets_detectes)  -> "[MASQUÉ: <codes séparés par ,>; sha256:<12 car.>]"
      - chaîne de plus de 160 caractères               -> "[<n> car.; sha256:<12 car.>] <60 premiers car.>…"
      - int, float, bool, None                         -> inchangée
      - autre (liste, dict)                            -> json.dumps(...) ; empreinte si plus de 160 caractères
    Utiliser _sha(texte). Tant que ce TODO n'est pas fait, le journal contient les arguments EN CLAIR.
    """
    _ = (secrets_detectes, _sha)
    return dict(args or {})


def _sha(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _client(context: MiddlewareContext) -> str | None:
    try:
        params = context.fastmcp_context.session.client_params
        info = getattr(params, "client_info", None) or getattr(params, "clientInfo", None)
        return f"{info.name}/{info.version}" if info else None
    except Exception:  # noqa: BLE001 - selon transport/révision du protocole
        return None


class JournalAudit(Middleware):
    """Middleware FastMCP : journalise découvertes et appels d'outils."""

    def __init__(self, serveur: str):
        self.serveur = serveur

    async def on_list_tools(self, context: MiddlewareContext, call_next):
        outils = await call_next(context)
        ecrire({"trace_id": uuid.uuid4().hex, "server": self.serveur, "actor": acteur(),
                "client": _client(context), "event": "tools_list",
                "tools": sorted(getattr(t, "name", str(t)) for t in outils)})
        return outils

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        debut = time.perf_counter()
        nom = context.message.name
        evt: dict[str, Any] = {
            "trace_id": uuid.uuid4().hex, "server": self.serveur, "actor": acteur(),
            "client": _client(context), "event": "tool_call", "tool": nom,
            "args": masquer_arguments(dict(context.message.arguments or {})),
        }
        try:
            resultat = await call_next(context)
        except Refus as exc:
            evt.update(decision="refused", reason=exc.code, message=str(exc)[:300])
            raise
        except (PydanticValidationError, FastMCPValidationError) as exc:
            evt.update(decision="refused", reason="arguments_invalides", message=str(exc).splitlines()[0][:300])
            raise
        except ToolError as exc:
            cause = exc.__cause__
            if isinstance(cause, Refus):
                evt.update(decision="refused", reason=cause.code, message=str(cause)[:300])
            elif isinstance(cause, (PydanticValidationError, FastMCPValidationError)):
                evt.update(decision="refused", reason="arguments_invalides", message=str(exc).splitlines()[0][:300])
            else:
                evt.update(decision="error", reason=type(cause).__name__ if cause else "ToolError",
                           message=str(exc)[:300])
            raise
        except Exception as exc:  # noqa: BLE001
            evt.update(decision="error", reason=type(exc).__name__, message=str(exc)[:300])
            raise
        else:
            texte = "".join(getattr(c, "text", "") or "" for c in (getattr(resultat, "content", None) or []))
            structure = getattr(resultat, "structured_content", None) or {}
            evt.update(decision="allowed", result_sha256=_sha(texte), result_bytes=len(texte.encode("utf-8")))
            if isinstance(structure, dict):
                if structure.get("sources"):
                    evt["sources"] = structure["sources"][:20]
                if structure.get("injection_flags"):
                    evt["injection_flags"] = structure["injection_flags"]
                if structure.get("retrieval_mode"):
                    evt["retrieval_mode"] = structure["retrieval_mode"]
                if structure.get("degraded_reason"):
                    evt["degraded_reason"] = str(structure["degraded_reason"])[:200]
            return resultat
        finally:
            evt["duration_ms"] = round((time.perf_counter() - debut) * 1000, 1)
            ecrire(evt)


def journaliser_demarrage(serveur: str, **details: Any) -> None:
    ecrire({"trace_id": uuid.uuid4().hex, "server": serveur, "actor": acteur(), "event": "server_start",
            "pid": os.getpid(), **details})
