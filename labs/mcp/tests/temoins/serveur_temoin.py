"""Serveur MCP TÉMOIN pour les tests du client : révèle ce que le client lui transmet.

- variables_sensibles : noms (jamais les valeurs) des variables d'environnement sensibles reçues ;
- roots : dossiers annoncés par le client via la capacité MCP « roots » (s'il l'annonce) ;
- fuite : renvoie un faux secret (le client doit le masquer) ;
- ecrire_note : outil d'écriture qui se déclare destructif (test de cohérence de la configuration).
"""
import os
import re

from fastmcp import Context, FastMCP

SENSIBLE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)", re.IGNORECASE)
mcp = FastMCP("temoin")


@mcp.tool(annotations={"readOnlyHint": True})
def variables_sensibles() -> str:
    """Liste les noms de variables d'environnement sensibles visibles par ce processus."""
    noms = sorted(k for k in os.environ if SENSIBLE.search(k))
    return ",".join(noms) or "aucune"


@mcp.tool(annotations={"readOnlyHint": True})
async def roots(ctx: Context) -> str:
    """Renvoie les roots annoncées par le client, ou « non annoncées »."""
    try:
        resultat = await ctx.session.list_roots()
        return ",".join(str(r.uri) for r in resultat.roots) or "liste vide"
    except Exception as exc:  # noqa: BLE001
        return f"non annoncées ({type(exc).__name__})"


@mcp.tool(annotations={"readOnlyHint": True})
def fuite() -> str:
    """Renvoie un faux fichier de configuration contenant une clé (comme git_show d'un application.yml)."""
    return "notification:\n  api-key: FAUX-JETON-DEMO-0000-NE-PAS-UTILISER\n"  # gitleaks:allow (valeur factice)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
def ecrire_note(texte: str) -> str:
    """Écrit une note (outil destructif de démonstration, ne fait rien)."""
    return f"note ignorée ({len(texte)} car.)"


if __name__ == "__main__":
    mcp.run(show_banner=False)
