"""Réponse RAG sourcée : recherche dans l'index NeoFlow, puis génération par le fournisseur choisi.

    uv run python repondre.py "Pourquoi le niveau 2 le vendredi ?"                      # offline (défaut)
    uv run python repondre.py "Pourquoi le niveau 2 le vendredi ?" --fournisseur ollama  # modèle local
    uv run python repondre.py "…" --fournisseur neogen                                  # NéoGen souverain
    uv run python repondre.py "…" --fournisseur anthropic                               # Claude (clé requise)

Le même code sert les trois familles : seul le client change (rag_llm.py). Pour NéoGen et Ollama,
c'est l'API compatible OpenAI (`/v1/chat/completions`) appelée avec le client `openai` et un `base_url`.
"""
from __future__ import annotations

import argparse
import re
import sys
import time

from rag_common import load_config
from rag_llm import repondre
from search import MODES, Searcher


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Réponse sourcée à une question sur NeoFlow.")
    parser.add_argument("question", nargs="+")
    parser.add_argument("--fournisseur", help="offline | anthropic | ollama | neogen (défaut : config llm.fournisseur)")
    parser.add_argument("--mode", default="hybrid", choices=MODES)
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--config")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    fournisseur = args.fournisseur or cfg.get("llm", {}).get("fournisseur", "offline")
    question = " ".join(args.question)
    with Searcher(args.config) as s:
        t0 = time.perf_counter()
        hits = s.search(question, mode=args.mode, k=args.k)
        t_recherche = time.perf_counter() - t0
        try:
            gen = repondre(question, hits, fournisseur, cfg)
        except Exception as exc:  # fournisseur injoignable, clé absente, quota : le dire, sans masquer
            print(f"ERREUR fournisseur {fournisseur} : {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
    print(f"## {question}\n")
    print(gen.texte.strip())
    cites = sorted({int(n) for n in re.findall(r"\[P(\d+)\]", gen.texte)})
    print("\n### Sources")
    for i, h in enumerate(hits, start=1):
        marque = "citée" if i in cites else "non citée"
        print(f"[P{i}] {h['citation']} ({marque}){' · PÉRIMÉ' if h.get('stale') else ''}")
    invalides = [n for n in cites if n > len(hits)]
    print(f"\n_Fournisseur {gen.fournisseur} / {gen.modele} · recherche {t_recherche * 1000:.0f} ms · "
          f"génération {gen.secondes:.1f} s · tokens {gen.input_tokens} / {gen.output_tokens}"
          + (f" · citations invalides : {invalides}" if invalides else "") + "_")
    return 0


if __name__ == "__main__":
    sys.exit(main())
