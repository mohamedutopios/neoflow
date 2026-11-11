"""Réindexation incrémentale du RAG NeoFlow après un changement Git (lab J09).

Pipeline DÉTERMINISTE (aucun LLM) :  Git -> extraction -> embeddings/index -> validation

  plan       git diff --name-status -M depuis..cible, filtrage (motifs, taille) -> plan.json
  appliquer  extraction du contenu À LA CIBLE (git show), indexation des fichiers ajoutés/modifiés,
             suppression des fichiers supprimés/renommés, invalidation des mémoires touchées
  valider    l'index reflète la cible (fichiers, commit, empreinte) ; si OK seulement,
             le « dernier commit indexé » avance (sinon le prochain passage reprend le même delta)
  tout       les trois à la suite (usage local ; Kestra appelle les étapes séparément)

Idempotent : relancer sur la même cible ne fait rien. Verrou local contre deux passages simultanés
(dans Kestra : `concurrency.limit: 1`).

Indexeur : le lab RAG J05 (labs/rag/indexer.py, `run_index(cfg, incremental=True)`) est importé de
façon tolérante ; la validation compare alors son manifeste au contenu à la cible. À défaut (lab absent,
dépendances non installées, autre dépôt), un INDEX SIMULÉ (.etat/index_simule.json) reproduit le contrat
(chemin -> commit, empreinte, nombre de chunks) pour tester le pipeline sans Qdrant ni Ollama.

Exemples :
  python reindex_incremental.py tout --depuis HEAD~1
  python reindex_incremental.py --kestra plan --depuis "$AVANT" --jusqu-a "$APRES" --sortie plan.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path

import extensions
import gitutil
from config import ICI, charger, dossier_etat
from memoire import StoreMemoire


def maintenant() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ecrire_json_atomique(chemin: Path, donnees) -> None:
    tmp = chemin.with_suffix(chemin.suffix + ".tmp")
    tmp.write_text(json.dumps(donnees, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, chemin)  # atomique : jamais de fichier d'état à moitié écrit


def lire_json(chemin: Path, defaut):
    return json.loads(chemin.read_text(encoding="utf-8")) if chemin.is_file() else defaut


def inclus(chemin: str, cfg: dict) -> bool:
    def m(p: str) -> bool:
        return fnmatch(chemin, p) or (p.startswith("**/") and fnmatch(chemin, p[3:]))
    r = cfg["reindex"]
    return any(m(p) for p in r["inclure"]) and not any(m(p) for p in r["exclure"])


# ====================================================================== 1. plan (Git)
def planifier(depot: Path, cfg: dict, etat_dir: Path, depuis: str | None, jusqu_a: str = "HEAD") -> dict:
    cible = gitutil.resoudre(depot, jusqu_a)
    etat = lire_json(etat_dir / "index_state.json", {})
    if depuis and set(depuis) == {"0"}:   # push de création de branche : pas de commit « avant »
        depuis = None
    depuis = gitutil.resoudre(depot, depuis) if depuis else etat.get("dernier_commit_indexe")
    plan = {"depuis": depuis, "cible": cible, "cree_le": maintenant(), "a_indexer": [], "a_supprimer": [],
            "ignores": []}
    if depuis == cible:
        plan["mode"] = "a_jour"
        return plan
    if depuis is None:
        plan["mode"] = "complet"
        candidats = [gitutil.Changement("A", c) for c in gitutil.fichiers_suivis(depot, cible)]
    else:
        plan["mode"] = "incremental"
        candidats = gitutil.changements(depot, depuis, cible)
    taille_max = cfg["reindex"]["taille_max_ko"] * 1024
    classer = extensions.fonction(cfg, "classer_changements", classer_changements)
    plan.update(classer(candidats, lambda chemin: inclus(chemin, cfg),
                        lambda chemin: int(gitutil.git(depot, "cat-file", "-s", f"{cible}:{chemin}").strip()),
                        taille_max))
    return plan


def classer_changements(changements: list[gitutil.Changement], est_inclus, taille, taille_max: int) -> dict:
    """Référence (remplaçable par `extensions.classer_changements`, TP4) : delta Git -> plan.

    Renvoie {"a_indexer": [{"path", "statut"}], "a_supprimer": [chemin], "ignores": [{"path", "motif"}]}.
    - A, M, T, C : à indexer si inclus et pas trop gros ; sinon ignoré avec motif
    - D          : à supprimer (si le chemin était indexable)
    - R          : ancien chemin à supprimer, nouveau chemin traité comme un ajout
    """
    plan: dict = {"a_indexer": [], "a_supprimer": [], "ignores": []}
    for c in changements:
        if c.statut in ("D", "R") and c.ancien_chemin is not None and est_inclus(c.ancien_chemin):
            plan["a_supprimer"].append(c.ancien_chemin)          # ancien chemin d'un renommage
        if c.statut == "D":
            if est_inclus(c.chemin):
                plan["a_supprimer"].append(c.chemin)
            continue
        if not est_inclus(c.chemin):
            plan["ignores"].append({"path": c.chemin, "motif": "hors motifs d'indexation"})
            continue
        octets = taille(c.chemin)
        if octets > taille_max:
            plan["ignores"].append({"path": c.chemin, "motif": f"taille {octets // 1024} Ko > {taille_max // 1024} Ko"})
            continue
        plan["a_indexer"].append({"path": c.chemin, "statut": c.statut})
    return plan


# ====================================================================== 2-3. extraction + index
class IndexSimule:
    """Contrat minimal d'un index de code : chemin -> (commit, empreinte, nb_chunks)."""

    nom = "index simulé (.etat/index_simule.json)"

    def __init__(self, etat_dir: Path, cfg: dict):
        self.chemin = etat_dir / "index_simule.json"
        self.lignes_par_chunk = cfg["reindex"]["lignes_par_chunk_simule"]
        self.donnees = lire_json(self.chemin, {})

    def indexer(self, fichiers: list[dict], commit: str) -> dict:
        chunks = 0
        for f in fichiers:
            n = max(1, math.ceil(len(f["contenu"].splitlines()) / self.lignes_par_chunk))
            self.donnees[f["path"]] = {"commit": commit, "empreinte": gitutil.empreinte(f["contenu"]),
                                       "nb_chunks": n, "indexe_le": maintenant()}
            chunks += n
        ecrire_json_atomique(self.chemin, self.donnees)
        return {"fichiers": len(fichiers), "chunks": chunks}

    def supprimer(self, chemins: list[str]) -> dict:
        n = sum(1 for c in chemins if self.donnees.pop(c, None) is not None)
        ecrire_json_atomique(self.chemin, self.donnees)
        return {"supprimes": n}

    def valider(self, depot: Path, plan: dict) -> tuple[int, list[str], list[str]]:
        erreurs: list[str] = []
        for f in plan["a_indexer"]:
            e = self.donnees.get(f["path"])
            attendu = gitutil.empreinte(gitutil.contenu_a(depot, plan["cible"], f["path"]) or "")
            if e is None:
                erreurs.append(f"{f['path']} absent de l'index")
            elif e["commit"] != plan["cible"] or e["empreinte"] != attendu:
                erreurs.append(f"{f['path']} indexé à {e['commit'][:10]} (attendu {plan['cible'][:10]})")
        erreurs += [f"{c} supprimé du dépôt mais encore indexé" for c in plan["a_supprimer"] if c in self.donnees]
        return len(plan["a_indexer"]) + len(plan["a_supprimer"]), erreurs, []


class IndexLabRagJ05:
    """Adaptateur vers labs/rag (J05) : `indexer.run_index(cfg, incremental=True)`.

    L'indexeur J05 recalcule lui-même le delta par empreinte de fichier à partir de son manifeste
    et lit l'ARBRE DE TRAVAIL : HEAD doit donc être la cible (c'est le cas dans le clone Kestra).
    Notre plan Git sert de contrôle : la validation compare le manifeste J05 au contenu à la cible.
    """

    def __init__(self, module, rag_common, depot: Path, config_rag: str | None):
        self.module, self.rc, self.depot = module, rag_common, depot
        self.cfg_rag = rag_common.load_config(config_rag)
        self.nom = f"lab RAG J05 (indexer.run_index, stockage {self.cfg_rag['_storage_dir']})"

    def indexer(self, fichiers: list[dict], commit: str) -> dict:
        if gitutil.head(self.depot) != commit:
            raise RuntimeError("l'indexeur J05 lit l'arbre de travail : faire `git checkout` de la cible d'abord")
        manifeste = self.module.run_index(self.cfg_rag, incremental=True, quiet=True)
        return {"fichiers_plan": len(fichiers), "chunks": manifeste.get("chunks"), "points": manifeste.get("points"),
                "commit_index": manifeste.get("git", {}).get("commit")}

    def supprimer(self, chemins: list[str]) -> dict:
        return {"supprimes": len(chemins), "note": "retirés par run_index (fichiers absents du corpus)"}

    def valider(self, depot: Path, plan: dict) -> tuple[int, list[str], list[str]]:
        manifeste = self.rc.read_manifest(self.cfg_rag) or {}
        fichiers = manifeste.get("files", {})
        corpus = set(self.rc.select_corpus(self.cfg_rag).files)
        erreurs, infos, controles = [], [], 1
        commit_index = manifeste.get("git", {}).get("commit_full", "")
        if commit_index != plan["cible"]:
            erreurs.append(f"index construit à {commit_index[:10] or '?'} (attendu {plan['cible'][:10]})")
        for f in plan["a_indexer"]:
            if f["path"] not in corpus:
                infos.append(f"{f['path']} hors corpus J05 (liste blanche de labs/rag/config.yaml)")
                continue
            controles += 1
            attendu = self.rc.sha256_text(gitutil.contenu_a(depot, plan["cible"], f["path"]) or "")
            if fichiers.get(f["path"], {}).get("sha256") != attendu:
                erreurs.append(f"{f['path']} absent ou périmé dans le manifeste J05")
        for c in plan["a_supprimer"]:
            controles += 1
            if c in fichiers:
                erreurs.append(f"{c} supprimé du dépôt mais encore indexé")
        return controles, erreurs, infos


def choisir_index(cfg: dict, etat_dir: Path, depot: Path, simulation: bool):
    """Index réel du lab RAG si disponible et cohérent avec le dépôt, sinon index simulé (raison tracée)."""
    if simulation or cfg["rag"].get("activer") == "non":
        return IndexSimule(etat_dir, cfg), "simulation demandée"
    chemin = (ICI / cfg["rag"]["chemin_lab"]).resolve()
    if not (chemin / "indexer.py").is_file():
        return IndexSimule(etat_dir, cfg), f"labs/rag/indexer.py absent ({chemin})"
    if str(chemin) not in sys.path:
        sys.path.insert(0, str(chemin))
    try:
        import indexer as module  # type: ignore[import-not-found]
        import rag_common  # type: ignore[import-not-found]
    except Exception as exc:  # dépendances du lab RAG non installées, etc.
        return IndexSimule(etat_dir, cfg), f"lab RAG non importable : {type(exc).__name__}: {exc}"
    if not callable(getattr(module, "run_index", None)):
        return IndexSimule(etat_dir, cfg), "indexer.run_index introuvable : API du lab RAG différente"
    index = IndexLabRagJ05(module, rag_common, depot, cfg["rag"].get("config"))
    racine = Path(index.cfg_rag["_repo_root"]).resolve()
    if racine != Path(depot).resolve():
        return IndexSimule(etat_dir, cfg), (f"le lab RAG indexe {racine}, pas {depot} "
                                            "(régler NEOFLOW_REPO_ROOT ou rag.config)")
    return index, "lab RAG détecté"


def appliquer(depot: Path, cfg: dict, etat_dir: Path, plan: dict, simulation: bool) -> dict:
    t0 = time.monotonic()
    index, raison = choisir_index(cfg, etat_dir, depot, simulation)
    rapport = {"etape": "appliquer", "depuis": plan["depuis"], "cible": plan["cible"], "mode": plan["mode"],
               "index": index.nom, "raison_index": raison}
    if plan["mode"] == "a_jour":
        return {**rapport, "statut": "a_jour", "duree_s": 0}
    # Extraction : contenu lu À LA CIBLE, pas dans l'arbre de travail (reproductible, provenance exacte)
    fichiers = [{"path": f["path"], "contenu": gitutil.contenu_a(depot, plan["cible"], f["path"]) or ""}
                for f in plan["a_indexer"]]
    rapport["indexation"] = index.indexer(fichiers, plan["cible"])
    rapport["suppression"] = index.supprimer(plan["a_supprimer"])
    if plan["depuis"]:
        store = StoreMemoire(etat_dir / "memoire.db", cfg)
        m = store.invalider_depuis_git(depot, plan["depuis"], plan["cible"])
        rapport["memoire"] = {k: m[k] for k in ("invalidees", "relocalisees", "revalidees")}
    rapport["statut"] = "applique"
    rapport["duree_s"] = round(time.monotonic() - t0, 3)
    return rapport


# ====================================================================== 4. validation
def valider(depot: Path, cfg: dict, etat_dir: Path, plan: dict, simulation: bool) -> dict:
    index, _ = choisir_index(cfg, etat_dir, depot, simulation)
    controles, erreurs, infos = (0, [], []) if plan["mode"] == "a_jour" else index.valider(depot, plan)
    statut = "ok" if not erreurs else "echec"
    rapport = {"etape": "valider", "cible": plan["cible"], "index": index.nom, "controles": controles,
               "erreurs": erreurs, "infos": infos, "statut": statut}
    if statut == "ok":
        etat = lire_json(etat_dir / "index_state.json", {"historique": []})
        if etat.get("dernier_commit_indexe") != plan["cible"]:
            etat["dernier_commit_indexe"] = plan["cible"]
            etat.setdefault("historique", []).append({"cible": plan["cible"], "depuis": plan["depuis"],
                                                      "fichiers": len(plan["a_indexer"]), "le": maintenant()})
            etat["historique"] = etat["historique"][-50:]
            ecrire_json_atomique(etat_dir / "index_state.json", etat)
    return rapport


# ====================================================================== CLI
class Verrou:
    def __init__(self, chemin: Path, ttl_s: int = 3600):
        self.chemin, self.ttl_s = chemin, ttl_s

    def __enter__(self):
        if self.chemin.exists() and time.time() - self.chemin.stat().st_mtime > self.ttl_s:
            self.chemin.unlink()  # verrou abandonné par un passage tué
        try:
            fd = os.open(self.chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise SystemExit(3) from None
        os.write(fd, f"{os.getpid()} {maintenant()}".encode())
        os.close(fd)
        return self

    def __exit__(self, *exc):
        self.chemin.unlink(missing_ok=True)


def sortie_kestra(**valeurs) -> None:
    # Convention des tâches de script Kestra : une ligne ::{"outputs":{...}}:: sans espaces.
    print("::" + json.dumps({"outputs": valeurs}, separators=(",", ":"), ensure_ascii=False) + "::")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Réindexation incrémentale NeoFlow")
    p.add_argument("--depot", default=".")
    p.add_argument("--etat")
    p.add_argument("--config")
    p.add_argument("--simulation", action="store_true", help="index simulé même si le lab RAG est présent")
    p.add_argument("--kestra", action="store_true", help="émettre les sorties au format Kestra")
    sp = p.add_subparsers(dest="cmd", required=True)
    pl = sp.add_parser("plan")
    pl.add_argument("--depuis")
    pl.add_argument("--jusqu-a", default="HEAD")
    pl.add_argument("--sortie", default="plan.json")
    for nom in ("appliquer", "valider"):
        x = sp.add_parser(nom)
        x.add_argument("--plan", default="plan.json")
        x.add_argument("--rapport")
    t = sp.add_parser("tout")
    t.add_argument("--depuis")
    t.add_argument("--jusqu-a", default="HEAD")
    t.add_argument("--rapport")
    a = p.parse_args(argv)

    cfg, etat_dir = charger(a.config), dossier_etat(a.etat)
    depot = gitutil.racine_depot(a.depot)

    if a.cmd == "plan":
        plan = planifier(depot, cfg, etat_dir, a.depuis, a.jusqu_a)
        ecrire_json_atomique(Path(a.sortie), plan)
        print(f"plan {plan['mode']} {str(plan['depuis'])[:10]}..{plan['cible'][:10]} : "
              f"{len(plan['a_indexer'])} à indexer, {len(plan['a_supprimer'])} à supprimer, "
              f"{len(plan['ignores'])} ignoré(s)")
        if a.kestra:
            sortie_kestra(mode=plan["mode"], cible=plan["cible"], nb_a_indexer=len(plan["a_indexer"]),
                          nb_a_supprimer=len(plan["a_supprimer"]))
        return 0

    try:
        with Verrou(etat_dir / "reindex.lock"):
            if a.cmd == "tout":
                plan = planifier(depot, cfg, etat_dir, a.depuis, a.jusqu_a)
                rapports = [appliquer(depot, cfg, etat_dir, plan, a.simulation)]
                rapports.append(valider(depot, cfg, etat_dir, plan, a.simulation))
                rapport = {"plan": {k: plan[k] for k in ("mode", "depuis", "cible")} |
                           {"a_indexer": [f["path"] for f in plan["a_indexer"]], "a_supprimer": plan["a_supprimer"],
                            "ignores": plan["ignores"]}, "etapes": rapports}
                statut = rapports[-1]["statut"]
            else:
                plan = lire_json(Path(a.plan), None)
                if plan is None:
                    print(f"plan introuvable : {a.plan}", file=sys.stderr)
                    return 1
                rapport = (appliquer if a.cmd == "appliquer" else valider)(depot, cfg, etat_dir, plan, a.simulation)
                statut = rapport["statut"]
    except SystemExit as exc:
        if exc.code == 3:
            print("réindexation déjà en cours (verrou présent) : abandon", file=sys.stderr)
        raise
    texte = json.dumps(rapport, indent=2, ensure_ascii=False)
    if getattr(a, "rapport", None):
        Path(a.rapport).write_text(texte, encoding="utf-8")
    print(texte)
    if a.kestra:
        sortie_kestra(statut=statut, cible=plan["cible"])
    return 2 if statut == "echec" else 0


if __name__ == "__main__":
    sys.exit(main())
