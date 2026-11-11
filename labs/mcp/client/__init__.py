"""Client MCP du lab J06 : connecte les serveurs de `configs/mcp_client.json` et les expose à l'agent
du J4 sous forme de `neoagent.tools.Tool`, avec une politique de permissions dans le code.

    from client import outils_mcp, PolitiqueMCP
    outils = outils_mcp("labs/mcp/configs/mcp_client.json",
                        PolitiqueMCP(confirmer=confirmer_en_console, outils=["git_*", "rag_*"]))
"""
import sys
from pathlib import Path

_LAB = Path(__file__).resolve().parents[1]
if str(_LAB) not in sys.path:
    sys.path.insert(0, str(_LAB))      # « commun » (journal, garde-fous) partagé avec les serveurs

from client.config import ConfigInvalide, charger_config  # noqa: E402
from client.outil import SOURCE_TOOL, Tool  # noqa: E402
from client.pont import PolitiqueMCP, confirmer_en_console, encadrer, nom_expose, outils_mcp  # noqa: E402

__all__ = ["outils_mcp", "PolitiqueMCP", "Tool", "SOURCE_TOOL", "confirmer_en_console", "encadrer",
           "nom_expose", "charger_config", "ConfigInvalide"]
