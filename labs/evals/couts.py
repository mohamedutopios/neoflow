"""Coût d'une tâche à partir du champ `usage` des réponses de l'API Claude (J10).

Formule, par modèle m (prix par million de tokens, recopiés depuis la page tarifs) :

    coût_m = ( input_tokens               × p_input_m
             + output_tokens              × p_output_m
             + cache_read_input_tokens    × p_cache_read_m
             + cache_creation_input_tokens × p_cache_write_m ) / 1 000 000
    coût   = Σ_m coût_m

Aucun prix n'est codé ici : ils viennent d'un fichier YAML versionné (mesure/tarifs.example.yaml),
daté et sourcé. `cache_creation_input_tokens` (écriture du cache, champ du contrat neoagent) est compté au prix
`cache_write` ; un ancien journal sans ce champ donne 0 pour ce terme (et le lecteur l'avertit).
Un modèle « simule:… » (mode --offline des labs) coûte 0. Si un prix manque pour un modèle utilisé, le coût vaut None et la liste des
prix manquants est renvoyée : un coût partiel ne doit pas passer pour un coût complet.
"""
from __future__ import annotations

from pathlib import Path

CORRESPONDANCE = {
    "input_tokens": "input",
    "output_tokens": "output",
    "cache_read_input_tokens": "cache_read",
    "cache_creation_input_tokens": "cache_write",
}


def charger_tarifs(chemin: str | Path | None) -> dict:
    if not chemin:
        return {}
    import yaml  # dépendance du lab (pyproject.toml)
    data = yaml.safe_load(Path(chemin).read_text(encoding="utf-8")) or {}
    return data


def _prix_modele(tarifs: dict, modele: str) -> dict | None:
    modeles = tarifs.get("modeles") or {}
    nom = modele.split("/")[-1]
    if nom in modeles:
        return modeles[nom]
    # tolère un suffixe de version ou de date : claude-sonnet-5-5-20261001 → claude-sonnet-5-5
    candidats = [m for m in modeles if nom.startswith(m)]
    return modeles[max(candidats, key=len)] if candidats else None


def cout(usage_par_modele: dict[str, dict[str, int]], tarifs: dict) -> tuple[float | None, dict, list[str]]:
    """Renvoie (coût total ou None, détail par modèle, prix manquants)."""
    detail, manquants, total = {}, [], 0.0
    for modele, usage in usage_par_modele.items():
        if modele.startswith("simule:"):      # mode --offline des labs : aucun appel facturé
            detail[modele] = 0.0
            continue
        prix = _prix_modele(tarifs, modele)
        if prix is None:
            if any(usage.values()):
                manquants.append(f"{modele} : modèle absent du fichier de tarifs")
            continue
        c = 0.0
        for cle, n in usage.items():
            if not n:
                continue
            p = prix.get(CORRESPONDANCE.get(cle, cle))
            if p is None:
                manquants.append(f"{modele}.{CORRESPONDANCE.get(cle, cle)}")
                continue
            c += n * float(p) / 1_000_000
        detail[modele] = round(c, 6)
        total += c
    return (None if manquants else round(total, 6)), detail, manquants


def formule_texte(tarifs: dict) -> str:
    source = tarifs.get("source") or "page tarifs non renseignée"
    date = tarifs.get("date_releve") or "date non renseignée"
    devise = tarifs.get("devise") or "?"
    return (f"coût = Σ_modèles (input × p_input + output × p_output + cache_read × p_cache_read + "
            f"cache_creation × p_cache_write) / 10⁶ — prix en {devise} par million de tokens, {source}, relevés le {date}")
