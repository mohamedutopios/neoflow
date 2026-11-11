"""Client MCP minimal (stdio, négociation « legacy » comme OpenCode 1.19 par défaut) : sans LLM.

Sert aux démos (plan B quand l'agent dévie), aux tests et au diagnostic d'un serveur.

  uv run --project labs/mcp python labs/mcp/mcp_cli.py tickets tools
  uv run --project labs/mcp python labs/mcp/mcp_cli.py tickets call get_ticket '{"ticket_id": "NEO-142"}'
  uv run --project labs/mcp python labs/mcp/mcp_cli.py db call run_select '{"sql": "SELECT count(*) FROM demande"}'
  uv run --project labs/mcp python labs/mcp/mcp_cli.py rag resources
  uv run --project labs/mcp python labs/mcp/mcp_cli.py rag read rag://statut
  uv run --project labs/mcp python labs/mcp/mcp_cli.py git tools
  uv run --project labs/mcp python labs/mcp/mcp_cli.py autre tools --cmd "npx -y @modelcontextprotocol/server-filesystem@2.0.1 docs"

Options : --env CLE=VALEUR (répétable) ajouté à l'environnement du serveur ; --json pour une sortie brute.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

LAB = Path(__file__).resolve().parent
VERSION_GIT = "2026.10.19"
SERVEURS = {
    "rag": [sys.executable, str(LAB / "retriever_server.py")],
    "tickets": [sys.executable, str(LAB / "tickets_server.py")],
    "db": [sys.executable, str(LAB / "readonly_sql_server.py")],
    "git": ["uvx", f"mcp-server-git=={VERSION_GIT}", "--repository", "."],
}


def _texte(resultat) -> str:
    return "\n".join(getattr(c, "text", "") or str(c) for c in resultat.content)


async def principal(args: argparse.Namespace) -> int:
    if args.serveur == "autre" and not args.cmd:
        raise SystemExit("--cmd est obligatoire avec le serveur « autre »")
    commande = shlex.split(args.cmd) if args.cmd else SERVEURS[args.serveur]
    env = dict(os.environ)
    for paire in args.env or []:
        cle, _, val = paire.partition("=")
        env[cle] = val
    transport = StdioTransport(command=commande[0], args=commande[1:], env=env, cwd=os.getcwd())
    async with Client(transport, mode="legacy", timeout=60, init_timeout=120) as client:
        info = client.initialize_result
        if args.action != "call" or args.verbose:
            print(f"# serveur {info.server_info.name} {info.server_info.version} · protocole {client.protocol_version}",
                  file=sys.stderr)
        if args.action == "tools":
            outils = await client.list_tools()
            if args.json:
                print(json.dumps([o.model_dump(mode="json", by_alias=True, exclude_none=True) for o in outils],
                                 ensure_ascii=False, indent=2))
            else:
                taille = len(json.dumps([o.model_dump(mode="json", by_alias=True, exclude_none=True) for o in outils]))
                for o in outils:
                    a = o.annotations
                    drapeau = "lecture" if a and a.read_only_hint else "ÉCRITURE"
                    print(f"{o.name:<24} [{drapeau}] {(o.description or '').strip().splitlines()[0][:90]}")
                print(f"# {len(outils)} outils · définitions ≈ {taille} caractères (≈ {taille // 4} tokens)", file=sys.stderr)
        elif args.action == "call":
            arguments = json.loads(args.arguments or "{}")
            res = await client.call_tool(args.outil, arguments, raise_on_error=False)
            etat = "ERREUR (isError=true)" if res.is_error else "OK"
            print(f"# {args.outil} -> {etat}", file=sys.stderr)
            if res.structured_content and not res.is_error and not args.json:
                print(json.dumps(res.structured_content, ensure_ascii=False, indent=2))
            else:
                print(_texte(res))
            return 2 if res.is_error else 0
        elif args.action == "resources":
            for r in await client.list_resources():
                print(f"{r.uri}  {r.description or ''}")
            for t in await client.list_resource_templates():
                print(f"{t.uri_template}  (modèle) {t.description or ''}")
        elif args.action == "read":
            for bloc in await client.read_resource(args.outil):
                print(getattr(bloc, "text", bloc))
        elif args.action == "prompts":
            for p in await client.list_prompts():
                params = ", ".join(a.name for a in p.arguments or [])
                print(f"{p.name}({params})  {p.description or ''}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("serveur", choices=[*sorted(SERVEURS), "autre"])
    ap.add_argument("action", choices=["tools", "call", "resources", "read", "prompts"])
    ap.add_argument("outil", nargs="?", help="nom de l'outil (call) ou URI (read)")
    ap.add_argument("arguments", nargs="?", help="arguments JSON de l'outil")
    ap.add_argument("--cmd", help="commande complète d'un autre serveur stdio")
    ap.add_argument("--env", action="append", help="CLE=VALEUR pour le serveur")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    return asyncio.run(principal(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
