"""Accès au modèle : client Claude réel (SDK `anthropic`) ou modèle simulé déterministe (`--offline`).

Les deux exposent `creer(systeme, messages, outils) -> ReponseModele`. L'agent ne voit pas la différence :
c'est ce qui permet de tester la boucle, les garde-fous et les patterns sans clé ni coût, et de servir de
plan B en formation.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

MODELE_DEFAUT = "claude-sonnet-5-5"
MODELE_LEGER = "claude-haiku-5-5"
MODELE_PLANIFICATION = "claude-opus-5-5"

# Modèles pour lesquels le repli serveur « fallbacks: "default" » est disponible sur l'API Claude.
MODELES_AVEC_REPLI = {"claude-sonnet-5-5", "claude-opus-5-5"}
BETA_REPLI = "server-side-fallback-2026-07-01"


@dataclass
class ReponseModele:
    """Réponse normalisée d'un appel au modèle."""

    blocs: list[dict]                 # {"type": "text", "text"} ou {"type": "tool_use", "id", "name", "input"}
    brut: list[Any]                   # contenu à renvoyer tel quel dans l'historique (append-only)
    stop_reason: str                  # end_turn, tool_use, pause_turn, max_tokens, refusal
    usage: dict[str, int] = field(default_factory=dict)
    modele: str = MODELE_DEFAUT

    @property
    def texte(self) -> str:
        return "\n".join(b["text"] for b in self.blocs if b.get("type") == "text" and b.get("text"))

    @property
    def appels(self) -> list[dict]:
        return [b for b in self.blocs if b.get("type") == "tool_use"]


def _usage(objet: Any) -> dict[str, int]:
    cles = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    return {cle: int(getattr(objet, cle, 0) or 0) for cle in cles}


def _normaliser(bloc: Any) -> dict:
    type_ = getattr(bloc, "type", None)
    if type_ == "text":
        return {"type": "text", "text": bloc.text}
    if type_ == "tool_use":
        return {"type": "tool_use", "id": bloc.id, "name": bloc.name, "input": dict(bloc.input or {})}
    return {"type": type_}  # thinking, fallback… : conservés dans `brut`, ignorés par la logique


class ClientClaude:
    """Appel réel à l'API Claude (Messages API, tool use, boucle pilotée par neoagent).

    - clé lue par le SDK dans ANTHROPIC_API_KEY (ou un profil `ant auth login`), jamais en dur ;
    - cache de prompt automatique (`cache_control` de premier niveau) : outils, système et historique ;
    - `effort` « medium » par défaut, réglage recommandé pour le codage agentique sur Claude Sonnet 5.5 ;
    - repli serveur `fallbacks: "default"` (bêta) si le modèle le permet, pour qu'un refus de classifieur ne
      bloque pas la session ; désactivable avec `repli=False`.
    """

    def __init__(self, modele: str = MODELE_DEFAUT, *, max_tokens: int = 16_000, effort: str | None = "medium",
                 repli: bool = True, client: Any = None) -> None:
        if client is None:
            import anthropic  # import paresseux : le mode --offline n'a pas besoin du SDK

            client = anthropic.Anthropic()
        self._client = client
        self.modele = modele
        self.max_tokens = max_tokens
        self.effort = effort
        self.repli = repli and modele in MODELES_AVEC_REPLI

    def creer(self, systeme: str, messages: list[dict], outils: list[dict]) -> ReponseModele:
        params: dict[str, Any] = {
            "model": self.modele,
            "max_tokens": self.max_tokens,
            "system": systeme,
            "tools": outils,
            "messages": messages,
        }
        if self.effort:
            params["output_config"] = {"effort": self.effort}
        if self.repli:
            reponse = self._client.beta.messages.create(
                **params, betas=[BETA_REPLI], fallbacks="default", cache_control={"type": "ephemeral"},
            )
        else:
            reponse = self._client.messages.create(**params, cache_control={"type": "ephemeral"})
        return ReponseModele(blocs=[_normaliser(b) for b in reponse.content], brut=list(reponse.content),
                             stop_reason=reponse.stop_reason or "end_turn", usage=_usage(reponse.usage),
                             modele=getattr(reponse, "model", self.modele))


# ---------------------------------------------------------------------------------------------- simulé

MOTS_VIDES = {"dans", "pour", "avec", "sans", "les", "des", "une", "sur", "est", "que", "qui", "tâche",
              "tache", "implémente", "implemente", "ajoute", "corrige", "fichier", "projet", "neoflow"}


def _estimer(*parties: Any) -> int:
    return max(1, sum(len(p if isinstance(p, str) else json.dumps(p, ensure_ascii=False, default=str))
                      for p in parties) // 4)


def _bloc(b: dict) -> dict:
    """Accepte la forme API et la forme courte des scénarios : {"texte"} ou {"outil", "entree"}."""
    if "outil" in b:
        return {"type": "tool_use", "name": b["outil"], "input": b.get("entree", {})}
    if "texte" in b:
        return {"type": "text", "text": b["texte"]}
    return b


def derniers_resultats(messages: list[dict]) -> list[str]:
    """Textes des tool_result du dernier message utilisateur (utile aux politiques simulées)."""
    if not messages or messages[-1]["role"] != "user" or isinstance(messages[-1]["content"], str):
        return []
    return [str(b.get("content", "")) for b in messages[-1]["content"] if b.get("type") == "tool_result"]


class ModeleSimule:
    """Modèle déterministe hors ligne : tours scriptés, ou politique Python, jamais d'appel réseau.

    L'usage est estimé (4 caractères ≈ 1 token) et le cache simulé (le préfixe de la requête précédente est
    compté en `cache_read_input_tokens`) : budgets et mesures restent testables.
    """

    def __init__(self, tours: list[list[dict]] | None = None, *,
                 politique: Callable[[list[dict], list[dict]], list[dict]] | None = None,
                 modele: str = "simule-neoagent") -> None:
        self.tours = [[_bloc(b) for b in tour] for tour in (tours or [])]
        self.politique = politique
        self.modele = modele
        self.appels = 0
        self._precedent = 0
        self._ids = 0

    @classmethod
    def depuis_fichier(cls, chemin: Path | str) -> ModeleSimule:
        donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
        return cls(donnees["tours"], modele=donnees.get("modele", "simule-neoagent"))

    @classmethod
    def explorateur(cls) -> ModeleSimule:
        """Politique par défaut de --offline : lister, chercher, lire, diff, conclure. Ne modifie rien."""
        return cls(politique=_politique_exploration)

    def creer(self, systeme: str, messages: list[dict], outils: list[dict]) -> ReponseModele:
        if self.politique is not None:
            blocs = [_bloc(b) for b in self.politique(messages, outils)]
        elif self.appels < len(self.tours):
            blocs = copy.deepcopy(self.tours[self.appels])
        else:
            blocs = [{"type": "text", "text": "Scénario simulé terminé : rien de plus à faire."}]
        self.appels += 1
        for bloc in blocs:
            if bloc["type"] == "tool_use" and "id" not in bloc:
                self._ids += 1
                bloc["id"] = f"toolu_sim_{self._ids:04d}"
        stop = "tool_use" if any(b["type"] == "tool_use" for b in blocs) else "end_turn"
        invite = _estimer(systeme, outils, messages)
        cache = min(self._precedent, invite)
        sortie = _estimer(blocs)
        self._precedent = invite + sortie
        # Comme l'API : total en entrée = input_tokens + cache_read_input_tokens (+ écriture de cache, ici 0).
        usage = {"input_tokens": invite - cache, "output_tokens": sortie,
                 "cache_read_input_tokens": cache, "cache_creation_input_tokens": 0}
        return ReponseModele(blocs=blocs, brut=copy.deepcopy(blocs), stop_reason=stop, usage=usage, modele=self.modele)


def _politique_exploration(messages: list[dict], outils: list[dict]) -> list[dict]:
    noms = {o["name"] for o in outils}
    tache = messages[0]["content"] if isinstance(messages[0]["content"], str) else ""
    tour = sum(1 for m in messages if m["role"] == "assistant")
    mots = sorted({m.lower() for m in re.findall(r"[A-Za-zÀ-ÿ]{5,}", tache)} - MOTS_VIDES, key=lambda m: (-len(m), m))
    resultats = derniers_resultats(messages)
    if tour == 0 and "lister" in noms:
        return [{"texte": "Je commence par la structure du dépôt."}, {"outil": "lister", "entree": {"profondeur": 2}}]
    if tour == 1 and "chercher" in noms and mots:
        motif = "(?i)(" + "|".join(re.escape(m) for m in mots[:3]) + ")"
        return [{"texte": f"Je cherche {', '.join(mots[:3])}."},
                {"outil": "chercher", "entree": {"motif": motif, "max_resultats": 20}}]
    if tour == 2 and "lire_fichier" in noms and resultats and ":" in resultats[0] and resultats[0] != "aucun résultat":
        premier = resultats[0].split(":", 1)[0]
        return [{"texte": f"Je lis {premier}."}, {"outil": "lire_fichier", "entree": {"chemin": premier, "debut": 1, "fin": 40}}]
    if tour <= 3 and "git_diff" in noms and not any("git_diff" in json.dumps(m.get("content"), default=str)
                                                   for m in messages if m["role"] == "assistant"):
        return [{"outil": "git_diff", "entree": {"stat": True}}]
    vus = [r.split(":", 1)[0] for r in resultats if ":" in r][:3]
    return [{"texte": "Exploration simulée terminée (mode --offline) : aucun fichier modifié. "
                      + (f"Fichiers consultés : {', '.join(vus)}." if vus else "")}]
