"""Métriques de retrieval de référence (implémentation du lab).

Un composant de TP peut les remplacer (config.yaml > composants.metriques) : eval.py prend alors
chaque fonction du module du stagiaire et garde celles du lab pour les fonctions absentes.

Conventions :
- `trouves` : chemins des passages renvoyés, dans l'ordre (un même fichier peut apparaître deux fois) ;
- `attendus` : fichiers indispensables (base du Recall) ; `pertinents` : attendus + also_relevant ;
- on ne regarde que les k premiers passages.
"""
from __future__ import annotations


def recall_at_k(trouves: list[str], attendus: set[str], k: int) -> float | None:
    """Part des fichiers attendus présents dans le top-k ; None s'il n'y a aucun fichier attendu."""
    if not attendus:
        return None
    return len(set(trouves[:k]) & set(attendus)) / len(attendus)


def hit_at_k(trouves: list[str], pertinents: set[str], k: int) -> bool:
    """Vrai si au moins un passage du top-k vient d'un fichier pertinent."""
    return any(p in pertinents for p in trouves[:k])


def reciprocal_rank(trouves: list[str], pertinents: set[str], k: int) -> float:
    """1 / rang du premier passage pertinent dans le top-k, 0 s'il n'y en a pas."""
    for rang, chemin in enumerate(trouves[:k], start=1):
        if chemin in pertinents:
            return 1.0 / rang
    return 0.0


def precision_at_k(trouves: list[str], pertinents: set[str], k: int) -> float:
    """Passages pertinents du top-k divisés par k (un fichier répété compte à chaque passage)."""
    return sum(1 for p in trouves[:k] if p in pertinents) / k


def mrr(rangs_reciproques: list[float]) -> float | None:
    """Moyenne des rangs réciproques ; None pour une liste vide."""
    return sum(rangs_reciproques) / len(rangs_reciproques) if rangs_reciproques else None


NOMS = ("recall_at_k", "hit_at_k", "reciprocal_rank", "precision_at_k", "mrr")
