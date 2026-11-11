"""Type `Tool` de l'agent du J4 (`labs/agent/neoagent/tools.py`), importé de façon tolérante.

Si `neoagent` est installé ou présent dans `labs/agent/`, on réutilise SA classe : les outils MCP sont
alors des `neoagent.tools.Tool` à part entière. Sinon, on définit une dataclass de même forme
(contrat neoagent, voir labs/agent/README.md), suffisante pour les tests et la démo hors ligne.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Callable, Literal

LAB_AGENT = Path(__file__).resolve().parents[2] / "agent"   # labs/agent

try:
    from neoagent.tools import Tool  # type: ignore[import-not-found]
    SOURCE_TOOL = "neoagent"
except ImportError:
    if (LAB_AGENT / "neoagent" / "tools.py").is_file() and str(LAB_AGENT) not in sys.path:
        sys.path.append(str(LAB_AGENT))            # en fin de sys.path : ne masque pas nos modules
    try:
        from neoagent.tools import Tool  # type: ignore[import-not-found,no-redef]
        SOURCE_TOOL = "neoagent"
    except ImportError:                             # labs/agent absent ou incomplet : même forme

        @dataclass
        class Tool:  # type: ignore[no-redef]
            name: str                                # ^[a-z0-9_]{1,64}$
            description: str
            input_schema: dict                       # JSON Schema de l'entrée
            handler: Callable[[dict], str]           # renvoie du texte (données non fiables)
            risque: Literal["lecture", "ecriture", "execution"] = "lecture"
            apercu: Callable[[dict], str] | None = None   # aperçu montré à l'approbateur de l'agent

            def __post_init__(self) -> None:
                if not re.match(r"^[a-z0-9_]{1,64}$", self.name):
                    raise ValueError(f"nom d'outil invalide : {self.name!r}")
                if self.risque not in ("lecture", "ecriture", "execution"):
                    raise ValueError(f"risque inconnu : {self.risque!r}")
                if not isinstance(self.input_schema, dict) or self.input_schema.get("type") != "object":
                    raise ValueError(f"input_schema de {self.name} : objet JSON Schema attendu")

            def definition(self) -> dict:
                return {"name": self.name, "description": self.description, "input_schema": self.input_schema}

        SOURCE_TOOL = "local"

ACCEPTE_APERCU = any(f.name == "apercu" for f in fields(Tool))

__all__ = ["Tool", "SOURCE_TOOL", "ACCEPTE_APERCU"]
