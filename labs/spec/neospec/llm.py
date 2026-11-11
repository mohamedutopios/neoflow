"""Accès au modèle, derrière une interface minimale : `json(...) -> dict`.

Deux implémentations interchangeables :
- ClientClaude : SDK Python `anthropic`, sortie structurée (output_config.format = JSON Schema),
  streaming (sorties longues), prompt caching du prompt système, repli serveur en cas de refus ;
- ClientSimule : déterministe, sans réseau ni clé (`--offline`). Rejoue les réponses enregistrées
  dans fixtures/offline/<TYPE>/, ou produit une réponse générique pour les autres variantes.
  Il sert aux tests, à la préparation des démos et de plan B.
"""
from __future__ import annotations

import copy
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import anthropic

from neospec import config


class RefusModele(RuntimeError):
    """stop_reason == "refusal" : pas de nouvelle tentative, escalade humaine."""


class SortieTronquee(RuntimeError):
    """stop_reason == "max_tokens" : la sortie JSON est incomplète."""


class ErreurAPI(RuntimeError):
    """Erreur d'appel non récupérable par le SDK (après ses propres nouvelles tentatives)."""


class ClientLLM(Protocol):
    def json(self, *, etape: str, systeme: str, message: str, schema: dict[str, Any]) -> dict[str, Any]: ...


# ------------------------------------------------------------------ journal d'usage
@dataclass
class Journal:
    """Une ligne JSON par appel : étape, modèle, usage, durée. Lu en J10 pour mesurer les coûts."""

    chemin: Path | None = None
    lignes: list[dict[str, Any]] = field(default_factory=list)

    def ecrire(self, evenement: dict[str, Any]) -> None:
        evenement = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **evenement}
        self.lignes.append(evenement)
        if self.chemin:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            with self.chemin.open("a", encoding="utf-8") as f:
                f.write(json.dumps(evenement, ensure_ascii=False) + "\n")


def _usage(reponse: Any) -> dict[str, int]:
    u = getattr(reponse, "usage", None)
    return {
        k: int(getattr(u, k, 0) or 0)
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    }


# ------------------------------------------------------------------ client réel
class ClientClaude:
    """Appel de l'API Claude avec sortie structurée.

    `client` peut être injecté (tests : doublure qui imite `beta.messages.stream`).
    La clé est lue dans l'environnement par le SDK (ANTHROPIC_API_KEY ou profil `ant auth login`).
    """

    def __init__(self, client: Any | None = None, journal: Journal | None = None, repli: bool = True,
                 max_tokens: int = config.MAX_TOKENS):
        self._client = client if client is not None else anthropic.Anthropic(max_retries=2)
        self.journal = journal or Journal()
        self.repli = repli
        self.max_tokens = max_tokens

    def json(self, *, etape: str, systeme: str, message: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Un appel à sortie structurée ; renvoie le JSON produit par le modèle.

        - modèle et effort selon l'étape (config.MODELES, config.EFFORTS) ; aucun temperature ni thinking ;
        - prompt système en bloc unique avec cache_control (préfixe mis en cache) ;
        - output_config.format = {"type": "json_schema", "schema": schema} ;
        - repli serveur si self.repli : betas=["server-side-fallback-2026-07-01"], fallbacks="default" ;
        - streaming (self._client.beta.messages.stream) et get_final_message() : sorties longues ;
        - erreurs du SDK traduites en ErreurAPI (de la plus spécifique à la plus générale) ;
        - usage journalisé ; stop_reason "refusal" → RefusModele, "max_tokens" → SortieTronquee.
        """
        # TODO TP1 : construire les paramètres (model = config.MODELES[etape], max_tokens, system avec cache_control, messages, output_config = effort + format json_schema), ajouter betas et fallbacks si self.repli, appeler self._client.beta.messages.stream(**parametres) puis get_final_message(), traduire les erreurs du SDK en ErreurAPI, journaliser l'usage, lever RefusModele / SortieTronquee selon stop_reason, renvoyer json.loads du premier bloc text.
        raise NotImplementedError("TODO TP1 : ClientClaude.json")


# ------------------------------------------------------------------ client simulé (offline)
DEFAUTS = ("gherkin", "gherkin-persistant", "openapi", "tracabilite")


class ClientSimule:
    """Modèle simulé déterministe. Aucun appel réseau, aucune clé.

    - `questions` et `generation` : rejoue fixtures/offline/<TYPE>/<etape>.json si présent,
      sinon produit une réponse générique construite à partir du ticket ou des décisions ;
    - `correction` : renvoie la génération sans défaut (le « modèle » corrige) ;
    - `defaut` injecte une erreur dans la première génération, pour exercer la boucle de
      correction : gherkin (en-tête de langue et étiquette retirés), openapi (operationId
      retiré), tracabilite (ligne de matrice retirée), gherkin-persistant (la correction
      échoue aussi : la boucle doit s'arrêter à sa borne).
    """

    def __init__(self, type_: str, defaut: str | None = None, fixtures: Path | None = None,
                 journal: Journal | None = None):
        if defaut is not None and defaut not in DEFAUTS:
            raise ValueError(f"Défaut simulé inconnu : {defaut} (attendu : {', '.join(DEFAUTS)})")
        self.type_ = type_
        self.defaut = defaut
        self.fixtures = fixtures or config.lab_dir() / "fixtures" / "offline"
        self.journal = journal or Journal()
        self.appels: list[dict[str, str]] = []

    def _fixture(self, etape: str) -> dict[str, Any] | None:
        chemin = self.fixtures / self.type_ / f"{etape}.json"
        return json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else None

    def json(self, *, etape: str, systeme: str, message: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.appels.append({"etape": etape, "message": message})
        if etape == "questions":
            sortie = self._fixture("questions") or questions_generiques(message)
        elif etape in ("generation", "correction"):
            base = self._fixture("generation") or generation_generique(self.type_, message)
            premiere = etape == "generation"
            if self.defaut and (premiere or self.defaut == "gherkin-persistant"):
                sortie = injecter_defaut(base, self.defaut)
            else:
                sortie = base
        else:
            raise ValueError(f"Étape inconnue : {etape}")
        self.journal.ecrire({
            "etape": etape, "modele": f"simule:{config.MODELES.get(etape, '?')}", "offline": True,
            "stop_reason": "end_turn",
            "usage": {"input_tokens": len(systeme + message) // 4, "output_tokens": len(json.dumps(sortie)) // 4,
                      "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        })
        return copy.deepcopy(sortie)


def creer_client(offline: bool, type_: str, defaut: str | None = None, journal: Journal | None = None) -> ClientLLM:
    if offline:
        return ClientSimule(type_, defaut=defaut, journal=journal)
    if defaut:
        raise ValueError("--offline-defaut n'a de sens qu'avec --offline")
    return ClientClaude(journal=journal)


def injecter_defaut(generation: dict[str, Any], defaut: str) -> dict[str, Any]:
    g = copy.deepcopy(generation)
    if defaut.startswith("gherkin") and g["features"]:
        contenu = g["features"][0]["contenu"]
        contenu = re.sub(r"\A#\s*language:[^\n]*\n", "", contenu)
        contenu = re.sub(r"^(\s*)@(?:[A-Z]{2,6}-)?(?:EF|ENF)-[\w-]+\s*\n(\s*Règle:)", r"\2", contenu, count=1,
                         flags=re.M)
        g["features"][0]["contenu"] = contenu
    elif defaut == "openapi":
        g["openapi_delta"] = re.sub(r"^(\s*)operationId:[^\n]*\n", "", g["openapi_delta"], count=1, flags=re.M)
    elif defaut == "tracabilite" and g["matrice"]:
        g["matrice"] = g["matrice"][1:]
    return g


# ------------------------------------------------------------------ réponses génériques (variantes sans fixture)
TERMES_VAGUES = (
    "raisonnable", "rapide", "simple", "assez", "comme d'habitude", "si possible", "sans exception",
    "ergonomique", "tout de suite", "souvent", "beaucoup", "trop", "exceptionnel", "on verra", "à voir",
)


def _phrases(texte: str) -> list[str]:
    return [p.strip(" -*\t") for p in re.split(r"(?<=[.;:!?])\s+|\n", texte) if len(p.strip()) > 15]


def questions_generiques(message: str) -> dict[str, Any]:
    """Heuristique hors ligne : une question par phrase contenant un terme vague ou une obligation."""
    ticket = message.split("<ticket>")[-1].split("</ticket>")[0] if "<ticket>" in message else message
    questions, termes, vus = [], [], set()
    for phrase in _phrases(ticket):
        bas = phrase.lower()
        terme = next((t for t in TERMES_VAGUES if t in bas), None)
        obligation = re.search(r"\b(il faut|doit|ne doit pas|obligatoire|ne surtout pas)\b", bas)
        if not (terme or obligation) or phrase in vus:
            continue
        vus.add(phrase)
        n = len(questions) + 1
        questions.append({
            "id": f"Q-{n:02d}",
            "question": f"Que signifie précisément « {terme or phrase[:60]} » ? Quelle règle vérifiable en déduire ?",
            "source": f"Ticket : « {phrase[:160]} »",
            "priorite": "Bloquante" if obligation else "Importante",
            "hypothese": {"id": f"H-{n:02d}", "enonce": f"[hors ligne] Règle à préciser à partir de : {phrase[:120]}"},
        })
        if terme:
            termes.append({"terme": terme, "question": f"Quelle cible chiffrée pour « {terme} » ?"})
        if len(questions) == 12:
            break
    if not questions:
        questions.append({"id": "Q-01", "question": "Quelles règles métier le ticket impose-t-il exactement ?",
                          "source": "Ticket (ensemble)", "priorite": "Bloquante",
                          "hypothese": {"id": "H-01", "enonce": "[hors ligne] Règles à préciser avec le métier"}})
    commentaires = re.findall(r"\*\*([^*]+)\*\*[^\n]*\n+>\s*([^\n]+)", ticket)
    contradictions = [{"passages": [c[1][:160]], "explication": f"Commentaire de {c[0].split(',')[0]} à confronter à la description"}
                      for c in commentaires[:3]]
    return {"questions": questions, "contradictions": contradictions,
            "risques": [{"id": "R-01", "risque": "[hors ligne] Règles inventées par l'agent d'implémentation",
                         "mitigation": "Trancher chaque question avant le J4"}],
            "termes_a_chiffrer": termes}


def generation_generique(type_: str, message: str) -> dict[str, Any]:
    """Génération hors ligne minimale mais valide : une EF et un scénario par hypothèse validée."""
    m = re.search(r"<decisions>(.*?)</decisions>", message, re.S)
    decisions = json.loads(m.group(1)) if m else {"hypotheses": []}
    hyps = [h for h in decisions.get("hypotheses", []) if h.get("statut") == "Validée"] or [
        {"id": "H-01", "enonce": "Règle à préciser"}]
    s = config.slug(type_)
    exigences, regles, matrice, regles_gherkin = [], [], [], []
    for i, h in enumerate(hyps, start=1):
        ef, rm = f"EF-{i:02d}", f"RM-{i:02d}"
        code = f"{type_}_REGLE_{i:02d}"
        regles.append({"id": rm, "regle": h["enonce"], "code": code, "exemple": f"{code} : règle {h['id']} non respectée"})
        exigences.append({"id": ef, "titre": f"Règle {h['id']}", "priorite": "Must", "regles": [rm],
                          "enonce": f"Si une demande {type_} enfreint {h['id']} ({h['enonce'][:120]}), alors le système doit la refuser avec {code}.",
                          "verification": f"{s}_regles.feature @{ef}"})
        regles_gherkin.append(
            f"  @{ef}\n  Règle: {h['enonce'][:90].rstrip('.')}\n\n"
            f"    Scénario: Refus d'une demande qui enfreint {h['id']}\n"
            f"      Quand \"alice\" crée une demande {type_} qui enfreint {h['id']}\n"
            f"      Alors la création est refusée avec le code \"{code}\"\n")
        matrice.append({"exigence": ef, "regles": rm, "scenarios": f"`{s}_regles` › {h['id']} (1)",
                        "contrat": "creerDemande", "taches": "T02", "tests_prevus": f"Regle{type_.title().replace('_', '')}Test @Tag {ef}"})
    enf = [{"id": "ENF-01", "titre": "Performance", "enonce": f"POST /api/demandes ({type_}) répond en moins de 300 ms au 95e percentile sur le jeu de démo.",
            "preuve": "Mesure http.server.requests (J10)"},
           {"id": "ENF-02", "titre": "Compatibilité", "enonce": "Aucun changement cassant ; tests du socle verts ; legacy/ intact.",
            "preuve": "./mvnw test ; git diff --stat sur legacy/"}]
    for e in enf:
        matrice.append({"exigence": e["id"], "regles": "—", "scenarios": "—", "contrat": "creerDemande",
                        "taches": "T03", "tests_prevus": e["preuve"]})
    ids = ", ".join(x["id"] for x in exigences)
    feature = (f"# language: fr\n@{s} @api\nFonctionnalité: Règles de la variante {type_} [hors ligne]\n"
               f"  Afin d'obtenir une demande conforme\n  En tant que collaborateur demandeur\n"
               f"  Je veux que NeoFlow applique les règles validées\n\n"
               f"  Contexte:\n    Étant donné que la date du jour est le \"2026-11-16\"\n\n" + "\n".join(regles_gherkin))
    openapi = f"""openapi: 3.1.0
info:
  title: NeoFlow — delta d'API de la variante {type_} [hors ligne]
  version: 0.1.0
  summary: Delta minimal produit hors ligne.
  license:
    name: Usage interne Neosoft — formation
    url: https://www.neosoft.fr
servers:
  - url: http://localhost:8080
security:
  - basicAuth: []
tags:
  - name: Demandes
    description: Opérations du socle modifiées par la variante.
paths:
  /api/demandes:
    post:
      tags: [Demandes]
      operationId: creerDemande
      summary: Crée une demande au statut BROUILLON
      x-neoflow-delta: modifie
      x-exigences: [{ids}]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
      responses:
        '201':
          description: Demande créée.
        '400':
          $ref: '#/components/responses/Probleme'
        '422':
          $ref: '#/components/responses/Probleme'
components:
  securitySchemes:
    basicAuth:
      type: http
      scheme: basic
  responses:
    Probleme:
      description: Erreur au format ProblemDetail.
      content:
        application/problem+json:
          schema:
            type: object
"""
    return {
        "titre": f"Variante {type_} [hors ligne]",
        "contexte": "Spécification générique produite par le modèle simulé, à compléter avec un vrai modèle.",
        "user_stories": [{"id": "US-01", "story": f"En tant que collaborateur, je veux poser une demande {type_} conforme.", "invest": "À découper"}],
        "non_objectifs": [{"id": "NO-01", "objectif": "Tout ce qui n'est pas couvert par une hypothèse validée", "raison": "Hors ligne"}],
        "regles": regles, "exigences": exigences, "exigences_non_fonctionnelles": enf,
        "contraintes": [{"id": "C-01", "contrainte": "Le module legacy/ n'est pas modifié."}],
        "risques": [{"id": "R-01", "risque": "Spécification générique", "mitigation": "Relancer sans --offline"}],
        "features": [{"fichier": f"{s}_regles.feature", "contenu": feature}],
        "openapi_delta": openapi, "matrice": matrice,
        "plan": [
            {"id": "T00", "nature": "H", "tache": "Porte 4 : spécification acceptée", "depend_de": [], "exigences": [x["id"] for x in exigences],
             "fichiers": f"docs/specs/{type_}.md", "verification": f"uv run neospec valider --type {type_}"},
            {"id": "T01", "nature": "D", "tache": "Générer les squelettes de steps", "depend_de": ["T00"], "exigences": [],
             "fichiers": "backend/src/test/java/.../acceptance", "verification": "uv run neospec steps"},
            {"id": "T02", "nature": "A", "tache": f"Règle {type_} (RegleMetierDemande)", "depend_de": ["T00"], "exigences": [x["id"] for x in exigences],
             "fichiers": f"backend/src/main/java/com/neosoft/neoflow/{s.replace('-', '')}/", "verification": "./mvnw test"},
            {"id": "T03", "nature": "H", "tache": "Revue du diff et matrice", "depend_de": ["T01", "T02"], "exigences": ["ENF-01", "ENF-02"],
             "fichiers": f"docs/specs/{s}/MATRICE_TRACABILITE.md", "verification": "Chaque exigence a une preuve verte"}],
        "adr": {"titre": f"Placement des règles {type_}", "slug": f"regles-{s}", "contexte": "À compléter.",
                "options": [{"nom": "A", "description": "Bean RegleMetierDemande", "avantages": "Point d'extension du socle", "inconvenients": "—"},
                            {"nom": "B", "description": "Conditions dans DemandeService", "avantages": "Rapide", "inconvenients": "Pollue le socle"},
                            {"nom": "C", "description": "Bean Validation", "avantages": "Déclaratif", "inconvenients": "400 au lieu de 422"}],
                "recommandation": "Option A", "consequences_negatives": "À compléter", "indicateur_remise_en_cause": "À compléter",
                "exigences": [x["id"] for x in exigences]},
    }
