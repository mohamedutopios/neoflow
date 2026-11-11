"""Prompts système (stables : ils forment le préfixe mis en cache)."""
from pathlib import Path


def prompt(nom: str) -> str:
    return (Path(__file__).parent / f"{nom}.md").read_text(encoding="utf-8")
