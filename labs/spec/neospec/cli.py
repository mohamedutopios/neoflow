"""Interface en ligne de commande.

    uv run neospec questions --type CONGES --offline
    uv run neospec arbitrer  --type CONGES --reponses exemples/reponses_CONGES.yaml
    uv run neospec generer   --type CONGES --offline [--offline-defaut gherkin]
    uv run neospec valider   --type CONGES
    uv run neospec gherkin   chemin/vers/features [--type CONGES]
    uv run neospec contrat   chemin/vers/contrat.yaml [--type CONGES]
    uv run neospec steps     --type CONGES --types-parametres exemples/parametres_CONGES.yaml
    uv run neospec chaine    --type CONGES --reponses exemples/reponses_CONGES.yaml --offline

Codes de sortie : 0 succès ; 1 validation en échec ; 2 porte non franchie ou correction épuisée ;
3 erreur d'appel au modèle (refus, sortie tronquée ou invalide, réseau).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from neospec import config, rendu, steps_java
from neospec.arbitrage import PorteNonFranchie, appliquer_reponses, arbitrer_interactif, charger_reponses
from neospec.correction import boucle_correction
from neospec.generation import ecrire_artefacts, generer, lire_brouillons
from neospec.llm import DEFAUTS, ErreurAPI, Journal, RefusModele, SortieTronquee, creer_client
from neospec.questions import extraire_questions, lire_contexte_socle
from neospec.schemas import SortieInvalide
from neospec.validation import valider_tout


def _dossier_travail(racine: Path, type_: str) -> Path:
    return racine / "docs" / "specs" / config.slug(type_) / "neospec"


def _ecrire_json(racine: Path, chemin: Path, donnees: Any) -> Path:
    cible = rendu.chemin_autorise(racine, chemin)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cible


def _lire_json(chemin: Path) -> Any:
    if not chemin.exists():
        raise FileNotFoundError(f"Fichier absent : {chemin} (lancer l'étape précédente)")
    return json.loads(chemin.read_text(encoding="utf-8"))


def _client(args: argparse.Namespace):
    journal = Journal(Path(args.journal) if args.journal else config.lab_dir() / "journal" / f"{config.slug(args.type)}.jsonl")
    return creer_client(args.offline, args.type, getattr(args, "offline_defaut", None), journal)


def cmd_questions(args: argparse.Namespace) -> int:
    racine = Path(args.racine).resolve()
    ticket = Path(args.ticket) if args.ticket else racine / "docs" / "tickets" / f"{args.type}.md"
    questions = extraire_questions(_client(args), ticket.read_text(encoding="utf-8"), args.type, lire_contexte_socle(racine))
    sortie = _ecrire_json(racine, Path(args.sortie) if args.sortie else _dossier_travail(racine, args.type) / "questions.json", questions)
    print(f"{len(questions['questions'])} question(s), {len(questions['contradictions'])} contradiction(s) → {sortie}")
    for q in questions["questions"]:
        print(f"  {q['id']} [{q['priorite']}] {q['question']}")
    print("Prochaine étape : arbitrage humain (porte 1).")
    return 0


def cmd_arbitrer(args: argparse.Namespace) -> int:
    racine = Path(args.racine).resolve()
    travail = _dossier_travail(racine, args.type)
    questions = _lire_json(Path(args.questions) if args.questions else travail / "questions.json")
    if args.interactif:
        if not args.decideur:
            print("--decideur est obligatoire en mode interactif", file=sys.stderr)
            return 2
        decisions = arbitrer_interactif(questions, args.decideur)
    else:
        decisions = appliquer_reponses(questions, charger_reponses(Path(args.reponses)))
    sortie = _ecrire_json(racine, Path(args.sortie) if args.sortie else travail / "decisions.json", decisions)
    en_attente = [h["id"] for h in decisions["hypotheses"] if h["statut"] == "À valider"]
    print(f"Décisions → {sortie}" + (f" ; encore à valider : {', '.join(en_attente)}" if en_attente else " ; porte 1 franchissable"))
    return 0


def _generer_et_valider(args: argparse.Namespace, racine: Path, decisions: dict[str, Any], client) -> int:
    ticket = (racine / "docs" / "tickets" / f"{args.type}.md")
    texte_ticket = ticket.read_text(encoding="utf-8") if ticket.exists() else ""
    brouillons = lire_brouillons(racine, args.type)
    if brouillons:
        print(f"Brouillons humains transmis au modèle : docs/specs/{config.slug(args.type)}/brouillons/")
    generation = generer(client, texte_ticket, args.type, decisions, lire_contexte_socle(racine), brouillons)
    resultat = boucle_correction(client, racine, args.type, decisions, generation, max_corrections=args.max_corrections,
                                 ecrire=lambda r, t, d, g: ecrire_artefacts(r, t, d, g, forcer=args.forcer))
    _ecrire_json(racine, _dossier_travail(racine, args.type) / "generation.json", resultat.generation)
    for tour in resultat.historique:
        print(f"  tour {tour['tour']} : {tour['erreurs']} erreur(s), {tour['avertissements']} avertissement(s)")
    print(resultat.rapport.texte(f"Validation de {args.type}"))
    if not resultat.ok:
        ecrire_artefacts(racine, args.type, decisions, resultat.generation, statut="BROUILLON", forcer=args.forcer)
        print(f"Correction épuisée après {resultat.corrections} tentative(s) : spécification laissée en BROUILLON, intervention humaine requise.")
        return 2
    print(f"Spécification écrite au statut EN REVUE après {resultat.corrections} correction(s). Prochaine étape : relecture (porte 3).")
    return 0


def cmd_generer(args: argparse.Namespace) -> int:
    racine = Path(args.racine).resolve()
    decisions = _lire_json(Path(args.decisions) if args.decisions else _dossier_travail(racine, args.type) / "decisions.json")
    return _generer_et_valider(args, racine, decisions, _client(args))


def cmd_valider(args: argparse.Namespace) -> int:
    rapport = valider_tout(Path(args.racine), args.type, exiger_commits=args.exiger_commits)
    print(json.dumps(rapport.to_dict(), ensure_ascii=False, indent=1) if args.json else rapport.texte(f"Validation de {args.type}"))
    return 0 if rapport.ok else 1


class _TousConnus(dict):
    """Sans spécification de référence : toute étiquette d'exigence est acceptée."""

    def __contains__(self, cle: object) -> bool:
        return True


def _exigences(args: argparse.Namespace) -> dict[str, str]:
    from neospec.validation.tracabilite import lire_spec
    if args.type:
        spec = Path(args.racine) / "docs" / "specs" / f"{args.type}.md"
        if spec.exists():
            return lire_spec(spec.read_text(encoding="utf-8"))[1]
    return _TousConnus()


def cmd_gherkin(args: argparse.Namespace) -> int:
    from neospec.validation import Rapport
    from neospec.validation.gherkin import valider_features
    rapport = Rapport()
    fichiers = [f for chemin in args.fichiers for f in (sorted(Path(chemin).glob("*.feature")) if Path(chemin).is_dir() else [Path(chemin)])]
    couverture = valider_features(fichiers, _exigences(args), rapport)
    rapport.info("Couverture : " + (", ".join(f"{k} ({v})" for k, v in sorted(couverture.items())) or "aucune exigence"))
    print(rapport.texte("Contrôle des scénarios"))
    return 0 if rapport.ok else 1


def cmd_contrat(args: argparse.Namespace) -> int:
    from neospec.validation import Rapport
    from neospec.validation.openapi import valider_contrat
    rapport = Rapport()
    for f in args.fichiers:
        valider_contrat(Path(f), _exigences(args), rapport, f)
    print(rapport.texte("Contrôle du contrat"))
    return 0 if rapport.ok else 1


def cmd_steps(args: argparse.Namespace) -> int:
    racine = Path(args.racine).resolve()
    s = config.slug(args.type)
    features = sorted(Path(args.features).glob("*.feature")) if args.features else sorted(
        (racine / "docs" / "specs" / s / "features").glob("*.feature"))
    if not features:
        print("Aucun fichier .feature", file=sys.stderr)
        return 1
    types = steps_java.charger_types(Path(args.types_parametres) if args.types_parametres else None)
    paquet = args.paquet or f"com.neosoft.neoflow.acceptance.{s.replace('-', '')}"
    classe = f"{steps_java.nom_classe(args.type)}Steps"
    definitions = steps_java.unifier(steps_java.collecter_etapes(features), types)
    dossier = rendu.chemin_autorise(racine, Path(args.sortie) / paquet.replace(".", "/"))
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"{classe}.java").write_text(
        steps_java.generer_classe(definitions, paquet, classe, types, f"docs/specs/{s}/features"), encoding="utf-8")
    print(f"{len(definitions)} définition(s) d'étapes → {dossier / (classe + '.java')}")
    if args.runner:
        runner = f"Acceptance{steps_java.nom_classe(args.type)}Test"
        (dossier / f"{runner}.java").write_text(
            steps_java.generer_runner(paquet, runner, f"features/{s}", args.tags), encoding="utf-8")
        print(f"Lanceur → {dossier / (runner + '.java')} (copier les .feature dans src/test/resources/features/{s}/)")
    return 0


def cmd_chaine(args: argparse.Namespace) -> int:
    racine = Path(args.racine).resolve()
    client = _client(args)
    ticket = racine / "docs" / "tickets" / f"{args.type}.md"
    questions = extraire_questions(client, ticket.read_text(encoding="utf-8"), args.type, lire_contexte_socle(racine))
    travail = _dossier_travail(racine, args.type)
    _ecrire_json(racine, travail / "questions.json", questions)
    print(f"[1/5] {len(questions['questions'])} question(s) extraites du ticket")
    decisions = appliquer_reponses(questions, charger_reponses(Path(args.reponses)))
    _ecrire_json(racine, travail / "decisions.json", decisions)
    print(f"[2/5] décisions humaines appliquées ({args.reponses})")
    print("[3/5] génération puis [4/5] validation et correction bornée")
    code = _generer_et_valider(args, racine, decisions, client)
    if code != 0:
        return code
    args.features = None
    print("[5/5] squelettes de steps Cucumber-JVM")
    return cmd_steps(args)


def construire_parseur() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="neospec", description="Assistant de spécification NeoFlow (J03)")
    sous = p.add_subparsers(dest="commande", required=True)

    def commun(sp: argparse.ArgumentParser, modele: bool = False) -> None:
        sp.add_argument("--type", required=True, help="Type de demande, ex. CONGES")
        sp.add_argument("--racine", default=str(config.racine_par_defaut()), help="Racine du dépôt NeoFlow")
        if modele:
            sp.add_argument("--offline", action="store_true", help="Modèle simulé déterministe : aucun appel à l'API")
            sp.add_argument("--journal", help="Journal JSONL des appels (défaut : labs/spec/journal/<type>.jsonl)")

    def generation(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--offline-defaut", choices=DEFAUTS, help="Hors ligne : injecter un défaut dans la 1re génération")
        sp.add_argument("--max-corrections", type=int, default=2, help="Borne de la boucle de correction (défaut 2)")
        sp.add_argument("--forcer", action="store_true", help="Autoriser la réécriture d'une spécification PRÊTE")

    def steps(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--types-parametres", help="YAML des types de paramètres personnalisés")
        sp.add_argument("--paquet", help="Paquet Java (défaut : com.neosoft.neoflow.acceptance.<type>)")
        sp.add_argument("--sortie", default="backend/src/test/java", help="Dossier source Java de sortie")
        sp.add_argument("--runner", action="store_true", help="Générer aussi le lanceur JUnit Platform")
        sp.add_argument("--tags", default="@api and not @wip", help="Filtre d'étiquettes du lanceur")

    sp = sous.add_parser("questions", help="Étape 1 : ticket → questions et hypothèses")
    commun(sp, True)
    sp.add_argument("--ticket", help="Chemin du ticket (défaut : docs/tickets/<TYPE>.md)")
    sp.add_argument("--sortie", help="Fichier JSON de sortie")
    sp.set_defaults(fonction=cmd_questions)

    sp = sous.add_parser("arbitrer", help="Étape 2 : décisions humaines (porte 1)")
    commun(sp)
    sp.add_argument("--questions")
    groupe = sp.add_mutually_exclusive_group(required=True)
    groupe.add_argument("--reponses", help="Fichier YAML de réponses")
    groupe.add_argument("--interactif", action="store_true")
    sp.add_argument("--decideur", help="Nom et rôle du décideur (mode interactif)")
    sp.add_argument("--sortie")
    sp.set_defaults(fonction=cmd_arbitrer)

    sp = sous.add_parser("generer", help="Étapes 3 et 4 : génération, validation, correction bornée")
    commun(sp, True)
    generation(sp)
    sp.add_argument("--decisions")
    sp.set_defaults(fonction=cmd_generer)

    sp = sous.add_parser("valider", help="Étape 4 seule : contrôles déterministes")
    commun(sp)
    sp.add_argument("--exiger-commits", action="store_true", help="Chaque EF citée dans un commit [EF-xx]")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fonction=cmd_valider)

    for nom, aide, fonction in (("gherkin", "Contrôle autonome de fichiers .feature", cmd_gherkin),
                                ("contrat", "Contrôle autonome de contrats OpenAPI", cmd_contrat)):
        sp = sous.add_parser(nom, help=aide)
        sp.add_argument("fichiers", nargs="+")
        sp.add_argument("--type", help="Type de la spécification de référence (étiquettes connues)")
        sp.add_argument("--racine", default=str(config.racine_par_defaut()))
        sp.set_defaults(fonction=fonction)

    sp = sous.add_parser("steps", help="Étape 5 : squelettes de step definitions Cucumber-JVM")
    commun(sp)
    steps(sp)
    sp.add_argument("--features", help="Dossier des .feature (défaut : docs/specs/<type>/features)")
    sp.set_defaults(fonction=cmd_steps)

    sp = sous.add_parser("chaine", help="Étapes 1 à 5 avec un fichier de réponses")
    commun(sp, True)
    generation(sp)
    steps(sp)
    sp.add_argument("--reponses", required=True)
    sp.set_defaults(fonction=cmd_chaine)
    return p


def main(argv: list[str] | None = None) -> int:
    args = construire_parseur().parse_args(argv)
    try:
        return args.fonction(args)
    except PorteNonFranchie as e:
        print(f"✖ {e}", file=sys.stderr)
        return 2
    except rendu.EcritureInterdite as e:
        print(f"✖ {e}", file=sys.stderr)
        return 2
    except (RefusModele, SortieTronquee, SortieInvalide, ErreurAPI) as e:
        print(f"✖ {type(e).__name__} : {e}", file=sys.stderr)
        return 3
