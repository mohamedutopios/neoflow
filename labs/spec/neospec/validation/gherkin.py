"""Contrôle des scénarios : parseur officiel gherkin-official, puis règles de structure NeoFlow."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from gherkin.errors import CompositeParserException, ParserError
from gherkin.parser import Parser
from gherkin.token_scanner import TokenScanner

from neospec.config import RE_ID_SEUL
from neospec.validation.rapport import Rapport


def analyser(texte: str) -> dict[str, Any]:
    """AST Gherkin (dict). Lève CompositeParserException ou ParserError si la syntaxe est invalide."""
    return Parser().parse(TokenScanner(texte))


def ids_exigences(tags: list[dict[str, Any]]) -> set[str]:
    return {t["name"][1:] for t in tags if RE_ID_SEUL.match(t["name"][1:])}


def valider_features(fichiers: list[Path], exigences: dict[str, str], rapport: Rapport,
                     racine: Path | None = None) -> dict[str, int]:
    """Valide chaque fichier .feature et renvoie la couverture {exigence: nombre de scénarios}.

    Erreurs :
    - première ligne non vide différente de « # language: <code> » ;
    - erreur de syntaxe Gherkin (premier message du parseur) ;
    - scénario sans étiquette d'exigence, ni directe, ni héritée (fonctionnalité, règle, exemples) ;
    - étiquette d'exigence inconnue de la spécification ;
    - plan du scénario sans ligne d'exemples ;
    - scénario sans étape « Alors » (Outcome ; une conjonction prend le type de l'étape précédente).
    Avertissements :
    - plus d'une action « Quand », action après un résultat, plus de 10 étapes ;
    - titre de scénario dupliqué dans le fichier ;
    - Contexte contenant autre chose que des « Étant donné ».
    """
    # TODO TP2 : pour chaque fichier : en-tête de langue, analyser(texte), parcours fonctionnalité → règles → scénarios avec héritage des étiquettes, contrôles des étapes (keywordType), retour de la couverture.
    raise NotImplementedError("TODO TP2 : valider_features")
