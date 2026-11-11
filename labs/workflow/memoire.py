"""Mémoire persistante gouvernée pour l'assistant NeoFlow (lab J09).

Chaque souvenir porte : un type (sémantique, épisodique, procédurale), un contenu, une
portée (projet:/client:/equipe:/utilisateur:), une provenance immuable fichier@commit
(+ lignes et empreinte de l'extrait cité), une date d'expiration et un statut.

Règles de gouvernance appliquées à l'écriture :
  - pas de fait (sémantique) ni de procédure sans provenance vérifiable dans Git ;
  - jamais « HEAD » stocké : le commit est résolu en SHA ;
  - portée obligatoire et lecture limitée aux portées demandées (pas de fuite entre clients) ;
  - contenu refusé s'il ressemble à un secret ;
  - TTL par défaut selon le type.
Règles appliquées à la lecture et après un changement Git :
  - souvenirs expirés ou invalidés jamais renvoyés ;
  - vérification paresseuse : si le fichier cité a changé depuis le commit du souvenir,
    l'extrait est recherché dans la nouvelle version (relocalisation) ou le souvenir est invalidé ;
  - invalidation en masse à partir d'un `git diff` (appelée par la réindexation incrémentale).

Usage CLI (exemples) :
  python memoire.py ajouter --type semantique --portee projet:neoflow \
      --contenu "Le niveau de validation est calculé par RegleValidationLegacy.determinerNiveau" \
      --source backend/src/main/java/com/neosoft/neoflow/legacy/RegleValidationLegacy.java@HEAD:21-22
  python memoire.py lister --portee projet:neoflow
  python memoire.py invalider --depuis HEAD~1 --jusqu-a HEAD
  python memoire.py exporter --portee projet:neoflow > ../../ia-toolbox/memoire/MEMOIRE_PROJET.md
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
import unicodedata
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import extensions
import gitutil
from config import charger, dossier_etat

TYPES = ("semantique", "episodique", "procedurale")
STATUTS = ("active", "invalide", "expiree")
PORTEE_RE = re.compile(r"^(projet|client|equipe|utilisateur):[a-z0-9._-]+$")
SECRETS_RE = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(password|mot[_ ]de[_ ]passe|passwd|secret|api[-_]?key|token)\s*[:=]\s*\S{6,}"),
]
MOTS_VIDES = {"les", "des", "une", "est", "dans", "pour", "par", "sur", "que", "qui", "quoi", "avec",
              "the", "and", "comment", "quel", "quelle", "quels", "quelles", "pas", "plus", "son", "ses"}


class MemoireRefusee(ValueError):
    """Écriture refusée par la politique de gouvernance."""


def maintenant() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(d: datetime | None) -> str | None:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def termes(texte: str) -> set[str]:
    t = unicodedata.normalize("NFKD", texte.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {m for m in re.findall(r"[a-z0-9_]{3,}", t) if m not in MOTS_VIDES}


# ---------------------------------------------------------------------- composants remplaçables (TP1)
def politique_par_defaut(type: str, contenu: str, portee: str, source: str | None) -> None:
    """Politique d'écriture de référence : lève MemoireRefusee si l'écriture est interdite.

    Remplaçable par `extensions.politique_memoire` (TP1). Ne vérifie que la proposition elle-même ;
    la résolution du SHA et la présence du fichier au commit sont vérifiées ensuite par le magasin.
    """
    if type not in TYPES:
        raise MemoireRefusee(f"type inconnu {type!r} (attendu : {', '.join(TYPES)})")
    if not PORTEE_RE.match(portee):
        raise MemoireRefusee(f"portée invalide {portee!r} (ex. projet:neoflow, client:acme)")
    if any(r.search(contenu) for r in SECRETS_RE):
        raise MemoireRefusee("contenu refusé : ressemble à un secret (clé, jeton, mot de passe)")
    if type in ("semantique", "procedurale") and not source:
        raise MemoireRefusee(f"une mémoire {type} exige une provenance fichier@commit")


def verdict_souvenir(extrait: str | None, debut: int | None, fin: int | None, empreinte: str | None,
                     contenu_nouveau: str | None) -> tuple[str, int | None, int | None]:
    """Sort d'un souvenir dont le fichier source a changé : (verdict, debut, fin).

    - fichier supprimé (`contenu_nouveau` None)            -> ("invalidee", None, None)
    - provenance sans lignes (`extrait` None)              -> ("invalidee", None, None) : prudence
    - lignes citées identiques (même empreinte)            -> ("inchangee", debut, fin)
    - extrait retrouvé ailleurs dans le fichier (déplacé)  -> ("relocalisee", nouveau_debut, nouvelle_fin)
    - sinon                                                -> ("invalidee", None, None)
    Remplaçable par `extensions.verdict_souvenir` (TP1).
    """
    if contenu_nouveau is None or not extrait:
        return "invalidee", None, None
    if gitutil.empreinte(gitutil.extrait(contenu_nouveau, debut, fin)) == empreinte:
        return "inchangee", debut, fin
    pos = gitutil.localiser(contenu_nouveau, extrait)
    if pos:
        return "relocalisee", pos[0], pos[1]
    return "invalidee", None, None


@dataclass
class Memoire:
    id: str
    type: str
    contenu: str
    portee: str
    source_fichier: str | None
    source_commit: str | None
    source_debut: int | None
    source_fin: int | None
    extrait: str | None
    empreinte: str | None
    auteur: str
    cree_le: str
    maj_le: str
    expire_le: str | None
    statut: str
    motif: str | None

    @property
    def provenance(self) -> str:
        if not self.source_fichier:
            return "(sans provenance)"
        lignes = f":{self.source_debut}-{self.source_fin}" if self.source_debut else ""
        return f"{self.source_fichier}@{(self.source_commit or '?')[:10]}{lignes}"


def analyser_source(source: str) -> tuple[str, str, int | None, int | None]:
    """'chemin@commit' ou 'chemin@commit:debut-fin' -> (chemin, commit, debut, fin)."""
    m = re.fullmatch(r"(?P<chemin>[^@]+)@(?P<commit>[^:]+)(?::(?P<d>\d+)-(?P<f>\d+))?", source.strip())
    if not m:
        raise MemoireRefusee(f"provenance illisible : {source!r} (attendu chemin@commit[:debut-fin])")
    d, f = m.group("d"), m.group("f")
    return m.group("chemin"), m.group("commit"), int(d) if d else None, int(f) if f else None


class StoreMemoire:
    def __init__(self, chemin_db: str | Path, config: dict | None = None, *, politique=None, verdict=None):
        self.cfg = config or charger()
        self.politique = politique or extensions.fonction(self.cfg, "politique_memoire", politique_par_defaut)
        self.verdict = verdict or extensions.fonction(self.cfg, "verdict_souvenir", verdict_souvenir)
        self.db = sqlite3.connect(str(chemin_db), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS memoire (
            id TEXT PRIMARY KEY, type TEXT NOT NULL, contenu TEXT NOT NULL, portee TEXT NOT NULL,
            source_fichier TEXT, source_commit TEXT, source_debut INTEGER, source_fin INTEGER,
            extrait TEXT, empreinte TEXT, auteur TEXT NOT NULL, cree_le TEXT NOT NULL, maj_le TEXT NOT NULL,
            expire_le TEXT, statut TEXT NOT NULL DEFAULT 'active', motif TEXT)""")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_mem_portee ON memoire(portee, statut)")
        self.db.commit()

    # ------------------------------------------------------------------ écriture
    def ajouter(self, type: str, contenu: str, portee: str, *, source: str | None = None,
                depot: str | Path | None = None, auteur: str = "humain", ttl_jours: int | None = -1,
                now: datetime | None = None) -> Memoire:
        now = now or maintenant()
        self.politique(type, contenu, portee, source)          # lève MemoireRefusee si refus
        if type not in TYPES or not PORTEE_RE.match(portee):    # garde du schéma de la base
            raise MemoireRefusee(f"type ou portée hors schéma : {type!r}, {portee!r}")

        fichier = commit = extrait = empr = None
        debut = fin = None
        if source:
            fichier, commit, debut, fin = analyser_source(source)
            if depot is not None:
                commit = gitutil.resoudre(depot, commit)  # jamais 'HEAD' en base
                contenu_fichier = gitutil.contenu_a(depot, commit, fichier)
                if contenu_fichier is None:
                    raise MemoireRefusee(f"provenance invérifiable : {fichier} absent à {commit[:10]}")
                if debut:
                    extrait = gitutil.normaliser(gitutil.extrait(contenu_fichier, debut, fin or debut))[:4000]
                    empr = gitutil.empreinte(extrait)
            elif not re.fullmatch(r"[0-9a-f]{7,40}", commit):
                raise MemoireRefusee("sans dépôt pour la résoudre, la provenance doit citer un SHA")

        if ttl_jours == -1:
            ttl_jours = self.cfg["memoire"]["ttl_jours"].get(type)
        expire = iso(now + timedelta(days=ttl_jours)) if ttl_jours else None

        doublon = self.db.execute(
            "SELECT id FROM memoire WHERE type=? AND portee=? AND contenu=? AND IFNULL(source_fichier,'')=? "
            "AND statut='active'", (type, portee, contenu.strip(), fichier or "")).fetchone()
        if doublon:  # idempotent : réécrire le même souvenir rafraîchit sa provenance
            self.db.execute("UPDATE memoire SET source_commit=?, source_debut=?, source_fin=?, extrait=?, "
                            "empreinte=?, maj_le=?, expire_le=? WHERE id=?",
                            (commit, debut, fin, extrait, empr, iso(now), expire, doublon["id"]))
            self.db.commit()
            return self.get(doublon["id"])

        mem = Memoire(id=uuid.uuid4().hex[:12], type=type, contenu=contenu.strip(), portee=portee,
                      source_fichier=fichier, source_commit=commit, source_debut=debut, source_fin=fin,
                      extrait=extrait, empreinte=empr, auteur=auteur, cree_le=iso(now), maj_le=iso(now),
                      expire_le=expire, statut="active", motif=None)
        champs = asdict(mem)
        self.db.execute(f"INSERT INTO memoire ({', '.join(champs)}) VALUES ({', '.join('?' * len(champs))})",
                        tuple(champs.values()))
        self.db.commit()
        return mem

    def marquer(self, id: str, statut: str, motif: str, now: datetime | None = None) -> None:
        assert statut in STATUTS
        self.db.execute("UPDATE memoire SET statut=?, motif=?, maj_le=? WHERE id=?",
                        (statut, motif, iso(now or maintenant()), id))
        self.db.commit()

    def oublier(self, id: str) -> bool:
        """Suppression physique (droit à l'oubli, fin de mission client)."""
        n = self.db.execute("DELETE FROM memoire WHERE id=?", (id,)).rowcount
        self.db.commit()
        return n > 0

    def oublier_portee(self, portee: str) -> int:
        n = self.db.execute("DELETE FROM memoire WHERE portee=?", (portee,)).rowcount
        self.db.commit()
        return n

    def purger(self, now: datetime | None = None) -> int:
        n = self.db.execute("UPDATE memoire SET statut='expiree', motif='TTL atteint', maj_le=? "
                            "WHERE statut='active' AND expire_le IS NOT NULL AND expire_le <= ?",
                            (iso(now or maintenant()), iso(now or maintenant()))).rowcount
        self.db.commit()
        return n

    # ------------------------------------------------------------------ lecture
    def get(self, id: str) -> Memoire | None:
        r = self.db.execute("SELECT * FROM memoire WHERE id=?", (id,)).fetchone()
        return Memoire(**dict(r)) if r else None

    def lister(self, portees: list[str] | None = None, statuts: tuple[str, ...] = ("active",),
               types: tuple[str, ...] = TYPES) -> list[Memoire]:
        sql = f"SELECT * FROM memoire WHERE statut IN ({','.join('?' * len(statuts))}) " \
              f"AND type IN ({','.join('?' * len(types))})"
        params: list = [*statuts, *types]
        if portees:
            sql += f" AND portee IN ({','.join('?' * len(portees))})"
            params += portees
        return [Memoire(**dict(r)) for r in self.db.execute(sql + " ORDER BY cree_le", params)]

    def rechercher(self, texte: str, portees: list[str], *, k: int = 5, depot: str | Path | None = None,
                   types: tuple[str, ...] = TYPES, now: datetime | None = None
                   ) -> tuple[list[Memoire], list[tuple[Memoire, str]]]:
        """Renvoie (souvenirs valides les plus pertinents, souvenirs écartés avec motif).

        `portees` est obligatoire : aucune lecture « globale » n'est possible.
        Si `depot` est fourni, la fraîcheur est vérifiée à la lecture (fichier modifié depuis le
        commit du souvenir) : on ne fait pas confiance au seul pipeline d'invalidation.
        """
        if not portees:
            raise ValueError("portées obligatoires pour lire la mémoire")
        now_iso = iso(now or maintenant())
        q = termes(texte)
        valides: list[tuple[float, Memoire]] = []
        ecartees: list[tuple[Memoire, str]] = []
        cible = gitutil.head(depot) if depot else None
        for mem in self.lister(portees, types=types):
            score = len(q & termes(mem.contenu)) / math.sqrt(len(termes(mem.contenu)) or 1)
            if score <= 0:
                continue
            if mem.expire_le and mem.expire_le <= now_iso:
                self.marquer(mem.id, "expiree", "TTL atteint")
                ecartees.append((mem, "expirée"))
                continue
            if cible and mem.source_fichier and mem.source_commit and mem.source_commit != cible:
                verdict = self._verifier(mem, depot, cible)
                if verdict == "invalidee":
                    ecartees.append((self.get(mem.id), self.get(mem.id).motif or "obsolète"))
                    continue
                mem = self.get(mem.id)
            valides.append((score, mem))
        valides.sort(key=lambda t: -t[0])
        return [m for _, m in valides[:k]], ecartees

    # ------------------------------------------------------------------ invalidation
    def invalider_depuis_git(self, depot: str | Path, depuis: str, jusqu_a: str = "HEAD") -> dict:
        """Invalide (ou relocalise) les souvenirs dont le fichier source a changé entre deux commits."""
        cible = gitutil.resoudre(depot, jusqu_a)
        depuis = gitutil.resoudre(depot, depuis)
        chgts = gitutil.changements(depot, depuis, cible)
        touches = {c.chemin: c for c in chgts} | {c.ancien_chemin: c for c in chgts if c.ancien_chemin}
        rapport = {"depuis": depuis, "jusqu_a": cible, "fichiers_modifies": len(chgts),
                   "invalidees": [], "relocalisees": [], "revalidees": []}
        for mem in self.lister():
            if mem.source_fichier in touches:
                verdict = self._verifier(mem, depot, cible, touches[mem.source_fichier])
                rapport[{"invalidee": "invalidees", "relocalisee": "relocalisees",
                         "inchangee": "revalidees"}[verdict]].append(
                    {"id": mem.id, "type": mem.type, "provenance": mem.provenance,
                     "motif": self.get(mem.id).motif})
        return rapport

    def _verifier(self, mem: Memoire, depot, cible: str, chgt: gitutil.Changement | None = None) -> str:
        chemin = mem.source_fichier
        if chgt and chgt.statut == "R" and chgt.ancien_chemin == mem.source_fichier:
            chemin = chgt.chemin
        if chgt is None and not gitutil.fichier_modifie_depuis(depot, mem.source_commit, chemin, cible):
            self._rafraichir(mem.id, chemin, cible, mem.source_debut, mem.source_fin, None)
            return "inchangee"
        contenu = gitutil.contenu_a(depot, cible, chemin)
        verdict, debut, fin = self.verdict(mem.extrait, mem.source_debut, mem.source_fin, mem.empreinte, contenu)
        if verdict == "inchangee":
            self._rafraichir(mem.id, chemin, cible, debut, fin, None)
        elif verdict == "relocalisee":
            self._rafraichir(mem.id, chemin, cible, debut, fin,
                             f"relocalisée L{mem.source_debut}-{mem.source_fin} -> L{debut}-{fin}")
        elif verdict == "invalidee":
            motif = (f"{chemin} supprimé à {cible[:10]}" if contenu is None else
                     f"{chemin} modifié entre {mem.source_commit[:10]} et {cible[:10]}" if not mem.extrait else
                     f"lignes citées modifiées entre {mem.source_commit[:10]} et {cible[:10]}")
            self.marquer(mem.id, "invalide", motif)
        else:
            raise ValueError(f"verdict inconnu {verdict!r} (attendu inchangee, relocalisee, invalidee)")
        return verdict

    def _rafraichir(self, id, chemin, commit, debut, fin, motif) -> None:
        self.db.execute("UPDATE memoire SET source_fichier=?, source_commit=?, source_debut=?, source_fin=?, "
                        "motif=?, maj_le=? WHERE id=?", (chemin, commit, debut, fin, motif, iso(maintenant()), id))
        self.db.commit()

    def revalider(self, depot: str | Path) -> dict:
        """Vérifie tous les souvenirs actifs contre HEAD (avant un export ou une session)."""
        cible = gitutil.head(depot)
        bilan = {"inchangee": 0, "relocalisee": 0, "invalidee": 0}
        for mem in self.lister():
            if mem.source_fichier and mem.source_commit and mem.source_commit != cible:
                bilan[self._verifier(mem, depot, cible)] += 1
        bilan["expiree"] = self.purger()
        return bilan

    # ------------------------------------------------------------------ export
    def exporter_markdown(self, portees: list[str]) -> str:
        lignes = ["<!-- Généré par labs/workflow/memoire.py exporter : ne pas éditer à la main -->",
                  f"# Mémoire projet ({', '.join(portees)})", "",
                  "Faits vérifiés avec leur provenance. Un fait sans provenance n'est pas une connaissance.", ""]
        for t, titre in (("semantique", "Faits"), ("procedurale", "Procédures"), ("episodique", "Épisodes récents")):
            mems = self.lister(portees, types=(t,))
            if mems:
                lignes.append(f"## {titre}")
                lignes += [f"- {m.contenu} — `{m.provenance}`" + (f" (expire {m.expire_le[:10]})" if m.expire_le else "")
                           for m in mems]
                lignes.append("")
        return "\n".join(lignes)


# ---------------------------------------------------------------------- CLI
def _ouvrir(args) -> StoreMemoire:
    return StoreMemoire(dossier_etat(args.etat) / "memoire.db", charger(args.config))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Mémoire gouvernée du lab workflow NeoFlow")
    p.add_argument("--etat", help="dossier d'état (défaut : labs/workflow/.etat)")
    p.add_argument("--config")
    p.add_argument("--depot", default=".", help="dépôt Git servant à vérifier les provenances")
    sp = p.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("ajouter")
    a.add_argument("--type", required=True, choices=TYPES)
    a.add_argument("--contenu", required=True)
    a.add_argument("--portee", required=True)
    a.add_argument("--source", help="chemin@commit[:debut-fin]")
    a.add_argument("--auteur", default="humain")
    a.add_argument("--ttl-jours", type=int, default=-1)
    lst = sp.add_parser("lister")
    lst.add_argument("--portee", action="append")
    lst.add_argument("--tous", action="store_true", help="inclure invalidées et expirées")
    r = sp.add_parser("rechercher")
    r.add_argument("texte")
    r.add_argument("--portee", action="append", required=True)
    inv = sp.add_parser("invalider")
    inv.add_argument("--depuis", required=True)
    inv.add_argument("--jusqu-a", default="HEAD")
    sp.add_parser("purger")
    o = sp.add_parser("oublier")
    o.add_argument("id")
    e = sp.add_parser("exporter")
    e.add_argument("--portee", action="append", required=True)
    e.add_argument("--revalider", action="store_true", help="vérifier les provenances contre HEAD avant export")
    args = p.parse_args(argv)
    store = _ouvrir(args)
    depot = gitutil.racine_depot(args.depot)

    if args.cmd == "ajouter":
        try:
            m = store.ajouter(args.type, args.contenu, args.portee, source=args.source, depot=depot,
                              auteur=args.auteur, ttl_jours=args.ttl_jours)
        except MemoireRefusee as exc:
            print(f"REFUSÉ : {exc}", file=sys.stderr)
            return 2
        print(f"ajoutée {m.id} [{m.type}] {m.provenance}")
    elif args.cmd == "lister":
        statuts = STATUTS if args.tous else ("active",)
        for m in store.lister(args.portee, statuts=statuts):
            print(f"{m.id}  {m.statut:<8} {m.type:<11} {m.portee:<18} {m.provenance}\n    {m.contenu}"
                  + (f"\n    motif : {m.motif}" if m.motif else ""))
    elif args.cmd == "rechercher":
        valides, ecartees = store.rechercher(args.texte, args.portee, depot=depot)
        for m in valides:
            print(f"OK      {m.id} {m.provenance} :: {m.contenu}")
        for m, motif in ecartees:
            print(f"ÉCARTÉE {m.id} {m.provenance} :: {motif}")
    elif args.cmd == "invalider":
        print(json.dumps(store.invalider_depuis_git(depot, args.depuis, args.jusqu_a), indent=2, ensure_ascii=False))
    elif args.cmd == "purger":
        print(f"{store.purger()} souvenir(s) expiré(s)")
    elif args.cmd == "oublier":
        print("supprimé" if store.oublier(args.id) else "introuvable")
    elif args.cmd == "exporter":
        if args.revalider:
            b = store.revalider(depot)
            print(f"<!-- revalidation à {gitutil.head(depot)[:10]} : {b} -->")
        print(store.exporter_markdown(args.portee))
    return 0


if __name__ == "__main__":
    sys.exit(main())
