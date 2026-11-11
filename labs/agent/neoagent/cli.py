"""CLI : uv run neoagent --repo CHEMIN --tache "..." [--pattern generator_verifier] [--mode vibe|structure]
[--offline] [--journal traj.jsonl] [--outils-externes module:fonction]

Codes retour : 0 tâche terminée (ou vérifiée), 1 arrêt sur une borne ou un échec, 2 erreur d'usage.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Callable

from neoagent.agent import SYSTEME_STRUCTURE, SYSTEME_VIBE, Agent
from neoagent.approbation import Approbateur
from neoagent.garde_fous import Politique
from neoagent.journal import Journal
from neoagent.modele import MODELE_DEFAUT, MODELE_PLANIFICATION, ModeleSimule
from neoagent.patterns.evaluator_optimizer import evaluateur_tracabilite, evaluator_optimizer
from neoagent.patterns.generator_verifier import generator_verifier
from neoagent.patterns.orchestrator_workers import DECOUPAGE_NEOFLOW, SousTache, orchestrer, synthese
from neoagent.patterns.plan_execute import plan_execute
from neoagent.patterns.react import react
from neoagent.patterns.routing import router
from neoagent.tools import Tool, outils_de_base
from neoagent.verificateurs import VerificateurCommande, verificateur_maven
from neoagent.worktrees import proposer_commit

PATTERNS = ("react", "plan_execute", "routing", "generator_verifier", "evaluator_optimizer", "orchestrator_workers")


def charger_outils_externes(spec: str, config: str | None = None) -> list[Tool]:
    """« module:fonction » ou « chemin/fichier.py:fonction » ; la fonction renvoie un Tool ou une liste de Tool.

    La fonction reçoit `config` (--outils-config) si elle accepte un paramètre : J05 `rag_tool(config_path=None)`,
    J06 `outils_mcp(config_path)`.
    """
    if ":" not in spec:
        raise ValueError(f"--outils-externes attend module:fonction, reçu {spec!r}")
    module_nom, fonction_nom = spec.rsplit(":", 1)
    if module_nom.endswith(".py"):
        chemin = Path(module_nom).resolve()
        definition = importlib.util.spec_from_file_location(chemin.stem, chemin)
        if definition is None or definition.loader is None:
            raise ImportError(f"module introuvable : {chemin}")
        module = importlib.util.module_from_spec(definition)
        sys.path.insert(0, str(chemin.parent))
        definition.loader.exec_module(module)
    else:
        module = importlib.import_module(module_nom)
    fonction = getattr(module, fonction_nom)
    accepte_config = bool(inspect.signature(fonction).parameters)
    produit = fonction(config) if accepte_config else fonction()
    elements = [produit] if not isinstance(produit, (list, tuple)) else list(produit)
    outils: list[Tool] = []
    for e in elements:
        if isinstance(e, Tool):
            outils.append(e)
        elif all(hasattr(e, a) for a in ("name", "description", "input_schema", "handler")):
            # Tool défini dans un autre environnement Python (même contrat) : on le reconstruit.
            outils.append(Tool(e.name, e.description, e.input_schema, e.handler, getattr(e, "risque", "lecture")))
        else:
            raise TypeError(f"{spec} doit renvoyer des Tool (name, description, input_schema, handler)")
    return outils


def construire_parseur() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="neoagent", description="Agent de développement NeoFlow (J04)")
    p.add_argument("--repo", required=True, type=Path, help="racine du dépôt ou du worktree")
    p.add_argument("--tache", required=True, help="tâche à réaliser (citer la spécification et la tâche du plan)")
    p.add_argument("--pattern", choices=PATTERNS, default="react")
    p.add_argument("--mode", choices=("vibe", "structure"), default="structure",
                   help="prompt système minimal (vibe) ou méthodique (structure) ; les garde-fous sont identiques")
    p.add_argument("--offline", action="store_true", help="modèle simulé déterministe, aucun appel à l'API")
    p.add_argument("--script", type=Path, help="scénario JSON rejoué par le modèle simulé (avec --offline)")
    p.add_argument("--journal", type=Path, help="journal de trajectoire JSONL")
    p.add_argument("--outils-externes", action="append", default=[], metavar="MODULE:FONCTION",
                   help="outils supplémentaires (J05 : agent_tool:rag_tool, J06 : outils_mcp)")
    p.add_argument("--outils-config", help="chemin de configuration transmis aux fonctions d'outils externes")
    p.add_argument("--ecriture", action="store_true", help="autorise l'écriture (politique générateur : tests protégés)")
    p.add_argument("--approbation", choices=("interactif", "refus", "accord"),
                   default="interactif" if sys.stdin.isatty() else "refus")
    p.add_argument("--modele", default=MODELE_DEFAUT)
    p.add_argument("--max-etapes", type=int, default=30)
    p.add_argument("--budget-tokens", type=int, default=200_000)
    p.add_argument("--timeout", type=float, default=None, help="délai global d'une session, en secondes")
    p.add_argument("--verificateur", help="commande du vérificateur (défaut : ./mvnw -q verify dans backend/)")
    p.add_argument("--verificateur-repertoire", default="backend")
    p.add_argument("--max-tours", type=int, default=3)
    p.add_argument("--exigences", default="", help="EF-01,EF-02… pour evaluator_optimizer")
    p.add_argument("--sous-taches", type=Path, help="JSON [{nom, consigne, perimetre, script?}] pour orchestrator_workers")
    p.add_argument("--commit", help="message de commit proposé à l'approbateur après une tâche réussie")
    return p


def main(argv: list[str] | None = None) -> int:
    args = construire_parseur().parse_args(argv)
    repo = args.repo.resolve()
    if not repo.is_dir():
        print(f"dépôt introuvable : {repo}", file=sys.stderr)
        return 2
    try:
        externes = [o for spec in args.outils_externes for o in charger_outils_externes(spec, args.outils_config)]
    except Exception as exc:  # noqa: BLE001 - message d'usage clair
        print(f"--outils-externes : {exc}", file=sys.stderr)
        return 2

    journal = Journal(args.journal)
    approbateur = Approbateur(args.approbation)
    systeme = SYSTEME_VIBE if args.mode == "vibe" else SYSTEME_STRUCTURE

    def client(script: Path | None = None) -> Any:
        if not args.offline:
            return None  # Agent crée le ClientClaude
        script = script or args.script
        return ModeleSimule.depuis_fichier(script) if script else ModeleSimule.explorateur()

    def agent(politique: Politique, modele: str = args.modele, script: Path | None = None) -> Agent:
        return Agent(outils_de_base(politique.racine, politique) + externes, modele=modele, max_etapes=args.max_etapes,
                     budget_tokens=args.budget_tokens, approbateur=approbateur, journal=journal, offline=args.offline,
                     client=client(script), systeme=systeme, timeout_s=args.timeout)

    def politique_travail(racine: Path, perimetre: tuple[str, ...] = ("*",)) -> Politique:
        return Politique.generateur(racine, perimetre) if args.ecriture else Politique.lecture(racine)

    verificateur = (VerificateurCommande(args.verificateur, args.verificateur_repertoire) if args.verificateur
                    else verificateur_maven())
    rapport: dict[str, Any] = {"pattern": args.pattern, "mode": args.mode, "offline": args.offline}
    ok = False

    if args.pattern == "react":
        r = react(agent(politique_travail(repo)), args.tache)
        ok, rapport["resultat"] = r.ok, _resume(r)
    elif args.pattern == "plan_execute":
        plan = plan_execute(agent(Politique.lecture(repo), MODELE_PLANIFICATION),
                            lambda: agent(politique_travail(repo)), args.tache, approbateur)
        ok = plan.statut == "termine"
        rapport.update(statut=plan.statut, plan=[e.etape for e in plan.plan], resultats=[_resume(r) for r in plan.resultats])
    elif args.pattern == "routing":
        routes: dict[str, Callable] = {
            "exploration": lambda t: agent(Politique.lecture(repo)).executer(t),
            "revue": lambda t: agent(Politique.lecture(repo), MODELE_PLANIFICATION).executer(t),
            "tests": lambda t: agent(Politique.redacteur_tests(repo) if args.ecriture else Politique.lecture(repo)).executer(t),
            "implementation": lambda t: agent(politique_travail(repo)).executer(t),
        }
        etiquette, r = router(args.tache, routes)
        ok = r.ok
        rapport.update(route=etiquette, resultat=_resume(r))
    elif args.pattern == "generator_verifier":
        gv = generator_verifier(agent(politique_travail(repo)), args.tache, verificateur, repo, args.max_tours)
        ok = gv.ok
        rapport.update(statut=gv.statut, tours=gv.tours, verdicts=[{"ok": v.ok, "commande": v.commande,
                                                                     "duree_s": v.duree_s} for v in gv.verdicts],
                       resultats=[_resume(r) for r in gv.resultats])
    elif args.pattern == "evaluator_optimizer":
        exigences = [e.strip() for e in args.exigences.split(",") if e.strip()]
        eo = evaluator_optimizer(agent(politique_travail(repo)), args.tache, evaluateur_tracabilite(repo, exigences),
                                 args.max_tours)
        ok = eo.statut == "accepte"
        rapport.update(statut=eo.statut, scores=[e.score for e in eo.evaluations])
    elif args.pattern == "orchestrator_workers":
        sous_taches, scripts = _sous_taches(args.sous_taches)
        resultats = orchestrer(repo, sous_taches,
                               lambda wt, st: agent(politique_travail(wt, st.perimetre), script=scripts.get(st.nom)))
        ok = all(r.resultat.ok for r in resultats)
        rapport.update(workers=[{"nom": r.sous_tache.nom, "worktree": str(r.worktree), **_resume(r.resultat)}
                                for r in resultats])
        print(synthese(resultats))

    if ok and args.commit and args.pattern != "orchestrator_workers":
        rapport["commit"] = proposer_commit(repo, args.commit, approbateur).motif
    print(json.dumps(rapport, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def _resume(r) -> dict:
    return {"statut": r.statut, "etapes": r.etapes, "tokens": r.tokens, "outils": r.appels_outils,
            "reponse": r.reponse[:2000]}


def _sous_taches(chemin: Path | None) -> tuple[list[SousTache], dict[str, Path]]:
    if chemin is None:
        return list(DECOUPAGE_NEOFLOW), {}
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    taches = [SousTache(d["nom"], d["consigne"], tuple(d.get("perimetre", ["*"]))) for d in donnees]
    scripts = {d["nom"]: (chemin.parent / d["script"]).resolve() for d in donnees if d.get("script")}
    return taches, scripts


if __name__ == "__main__":
    raise SystemExit(main())
