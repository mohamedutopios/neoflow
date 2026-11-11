"""Point d'entrée des outils MCP pour l'agent du J4 (`--outils-externes` de neoagent).

  uv run --project labs/agent --with "fastmcp>=4.1,<4.2" --with "jsonschema>=4.23,<5" python -m neoagent.cli \
    --repo . --tache "Instruis le ticket NEO-131" --approbation interactif \
    --outils-externes labs/mcp/neoagent_outils.py:outils_mcp --outils-config labs/mcp/configs/mcp_client.json

Les écritures (risque « ecriture ») sont validées par l'Approbateur de neoagent, qui montre l'aperçu fourni par
le client (`Tool.apercu`) ; le client n'accepte l'appel que pour ces arguments exacts. Les lectures marquées
« confirmation » (git_show) n'étant pas soumises à l'Approbateur, elles restent refusées dans ce mode.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from client import outils_mcp  # noqa: E402,F401

__all__ = ["outils_mcp"]
