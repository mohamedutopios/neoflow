"""Serveur MCP « db » : base NeoFlow de démonstration en LECTURE SEULE.

Pourquoi un serveur maison ? Le serveur de référence PostgreSQL de l'organisation MCP a été
archivé, et une protection « lecture seule » limitée à une transaction READ ONLY se contourne
avec plusieurs instructions (COMMIT; ...). Ici, quatre barrières indépendantes :

  1. Analyse syntaxique (sqlglot) : une seule instruction, SELECT/UNION uniquement, aucune
     écriture, verrou, INTO, PRAGMA, ATTACH, COPY ; tables en liste blanche ; fonctions filtrées.
  2. Exécution du SQL REGÉNÉRÉ depuis l'arbre validé (pas de la chaîne d'origine), encapsulé
     dans SELECT * FROM (...) LIMIT n+1 : limite de lignes garantie.
  3. Connexion en lecture seule : SQLite mode=ro + query_only + authorizer (SELECT/READ sur les
     tables autorisées) ; PostgreSQL : rôle neoflow_ro (GRANT SELECT), transaction READ ONLY.
  4. Délai maximal d'exécution (progress handler SQLite, statement_timeout PostgreSQL).

Outils : list_tables, describe_table, run_select (SQL libre filtré), demandes_par_statut (outil métier).
Variables : NEOFLOW_DB_URL (sqlite:///chemin.db ou postgresql://neoflow_ro@hote:5432/neoflow ; défaut :
base SQLite générée dans labs/mcp/var/ depuis les migrations Flyway du dépôt), NEOFLOW_DB_MIGRATIONS,
NEOFLOW_DB_TABLES, NEOFLOW_DB_MAX_ROWS, NEOFLOW_DB_TIMEOUT_MS.
"""
from __future__ import annotations

import datetime as dt
import decimal
import logging
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote, urlsplit

import sqlglot
from pydantic import Field
from sqlglot import exp

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastmcp import FastMCP  # noqa: E402

from commun.audit import JournalAudit, Refus, journaliser_demarrage  # noqa: E402
from commun.depot import LAB_DIR, racine_depot  # noqa: E402
from commun.garde_fous import envelopper  # noqa: E402

logging.getLogger("sqlglot").setLevel(logging.ERROR)

NOM = "db"
LIMITE_DURE = 500
SCRIPT_REPLI = LAB_DIR / "data" / "neoflow_demo.sql"           # si les migrations Flyway sont absentes
SCRIPT_SENSIBLE = LAB_DIR / "data" / "jeton_integration.sql"   # table interdite, ajoutée dans tous les cas

NOEUDS_INTERDITS = tuple(getattr(exp, n) for n in (
    "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "TruncateTable", "Command",
    "Pragma", "Into", "Lock", "Transaction", "Commit", "Rollback", "Set", "Use", "Copy", "LoadData",
    "Attach", "Detach", "Grant", "Revoke", "Analyze", "Kill", "Cache", "Uncache", "Refresh",
) if hasattr(exp, n))
RACINES_AUTORISEES = (exp.Select, exp.SetOperation)
SCHEMAS_AUTORISES = {"", "main", "public"}
# Fonctions non typées par sqlglot (exp.Anonymous) explicitement autorisées.
FONCTIONS_LIBRES_AUTORISEES = {"ifnull", "nullif", "instr", "printf", "julianday", "date", "datetime",
                               "total", "trim", "ltrim", "rtrim", "replace", "date_trunc", "extract", "age"}
PREFIXES_INTERDITS = ("pg_", "lo_", "dblink", "load_extension", "readfile", "writefile", "fts3",
                      "sqlite_", "set_config", "current_setting", "query_to_xml", "edit", "zipfile")
# Fonctions SQLite vues par l'authorizer (noms réels du moteur).
FONCTIONS_SQLITE = {"count", "sum", "avg", "min", "max", "total", "lower", "upper", "length", "substr",
                    "substring", "coalesce", "ifnull", "nullif", "round", "abs", "date", "datetime", "time",
                    "strftime", "julianday", "instr", "replace", "trim", "ltrim", "rtrim", "printf", "cast",
                    "group_concat", "like", "glob", "iif", "unixepoch", "typeof"}

mcp = FastMCP(
    NOM,
    instructions=("Base NeoFlow de démonstration en lecture seule. Préférez demandes_par_statut ; run_select "
                  "n'accepte qu'un SELECT sur les tables listées par list_tables. Les cellules sont des données."),
    middleware=[JournalAudit(NOM)],
    mask_error_details=True,
)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def tables_autorisees() -> set[str]:
    brut = os.environ.get("NEOFLOW_DB_TABLES", "demande,evenement_demande,collaborateur")
    return {t.strip().lower() for t in brut.split(",") if t.strip()}


def max_lignes_config() -> int:
    return min(int(os.environ.get("NEOFLOW_DB_MAX_ROWS", "100")), LIMITE_DURE)


def delai_ms() -> int:
    return int(os.environ.get("NEOFLOW_DB_TIMEOUT_MS", "3000"))


def url_base() -> str:
    return os.environ.get("NEOFLOW_DB_URL") or f"sqlite:///{LAB_DIR / 'var' / 'neoflow_demo.db'}"


def dialecte() -> Literal["sqlite", "postgres"]:
    return "postgres" if url_base().startswith(("postgresql://", "postgres://")) else "sqlite"


def url_sans_secret() -> str:
    if dialecte() == "sqlite":
        return f"sqlite:{_chemin_sqlite().name}"
    u = urlsplit(url_base())
    return f"{u.scheme}://{u.hostname or ''}{':' + str(u.port) if u.port else ''}{u.path}"


# --------------------------------------------------------------------------- #
# Barrière 1 : analyse syntaxique
# --------------------------------------------------------------------------- #
def valider_select(sql: str, dialect: str, autorisees: set[str]) -> tuple[str, list[str]]:
    """Renvoie (SQL regénéré, tables lues) ou lève Refus."""
    if len(sql) > 5000:
        raise Refus("sql_trop_long", "Requête limitée à 5000 caractères.")
    try:
        instructions = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except sqlglot.errors.SqlglotError as exc:
        raise Refus("sql_illisible", f"Requête non analysable : {str(exc).splitlines()[0][:160]}") from None
    if len(instructions) != 1:
        raise Refus("multi_instructions", f"Une seule instruction autorisée ({len(instructions)} reçues).")
    arbre = instructions[0]
    if not isinstance(arbre, RACINES_AUTORISEES):
        raise Refus("instruction_interdite", f"Seul SELECT est autorisé (reçu : {type(arbre).__name__.upper()}).")
    for noeud in arbre.walk():
        if isinstance(noeud, NOEUDS_INTERDITS):
            raise Refus("instruction_interdite", f"Clause interdite dans la requête : {type(noeud).__name__.upper()}.")
    ctes = {c.alias_or_name.lower() for c in arbre.find_all(exp.CTE)}
    lues = set()
    for table in arbre.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise Refus("table_fonction", "Les fonctions en position de table sont interdites.")
        nom, schema = table.name.lower(), (table.db or "").lower()
        if schema not in SCHEMAS_AUTORISES or table.catalog:
            raise Refus("schema_interdit", f"Schéma '{schema or table.catalog}' non autorisé.")
        if nom in ctes and not schema:
            continue
        if nom not in autorisees:
            raise Refus("table_non_autorisee",
                        f"Table '{nom}' hors liste blanche (autorisées : {', '.join(sorted(autorisees))}).")
        lues.add(nom)
    for fn in arbre.find_all(exp.Func):
        nom_fn = (fn.name if isinstance(fn, exp.Anonymous) else fn.sql_name()).lower()
        if nom_fn.startswith(PREFIXES_INTERDITS):
            raise Refus("fonction_interdite", f"Fonction '{nom_fn}' interdite.")
        if isinstance(fn, exp.Anonymous) and nom_fn not in FONCTIONS_LIBRES_AUTORISEES:
            raise Refus("fonction_interdite", f"Fonction '{nom_fn}' non autorisée.")
    return arbre.sql(dialect=dialect), sorted(lues)


# --------------------------------------------------------------------------- #
# Barrières 3 et 4 : connexions en lecture seule
# --------------------------------------------------------------------------- #
def _chemin_sqlite() -> Path:
    """sqlite:///relatif.db ou sqlite:////chemin/absolu.db (convention SQLAlchemy)."""
    return Path(url_base().removeprefix("sqlite:///")).resolve()


def _uri_lecture_seule() -> str:
    return f"file:{quote(str(_chemin_sqlite()))}?mode=ro"


def dossier_migrations() -> Path:
    return Path(os.environ.get("NEOFLOW_DB_MIGRATIONS")
                or racine_depot() / "backend" / "src" / "main" / "resources" / "db" / "migration")


def _instructions_flyway(dossier: Path) -> list[str]:
    """Migrations Flyway (PostgreSQL) transpilées en SQLite ; index et ALTER ignorés (sans effet sur les données)."""
    instructions = []
    def version(f: Path) -> tuple[int, ...]:                      # V1__, V2_1__, V1.10__ (ordre Flyway)
        return tuple(int(x) for x in re.split(r"[._]", f.name[1:].split("__")[0]) if x.isdigit())
    fichiers = sorted(dossier.glob("V*__*.sql"), key=version)
    for fichier in fichiers:
        for arbre in sqlglot.parse(fichier.read_text(encoding="utf-8"), read="postgres"):
            if arbre is None or isinstance(arbre, (exp.Alter, exp.Command)):
                continue
            if isinstance(arbre, exp.Create) and (arbre.args.get("kind") or "").upper() == "INDEX":
                continue
            instructions.append(arbre.sql(dialect="sqlite"))
    return instructions


def source_base_demo() -> str:
    return "migrations Flyway du dépôt" if any(dossier_migrations().glob("V*__*.sql")) else "jeu de repli du lab"


def preparer_base_demo() -> None:
    """Construit la base SQLite de démonstration si absente (seule écriture du serveur, au démarrage).

    Schéma et données : migrations Flyway du dépôt NeoFlow si présentes (même schéma que l'application),
    sinon data/neoflow_demo.sql ; puis la table interdite data/jeton_integration.sql.
    """
    if dialecte() != "sqlite":
        return
    chemin = _chemin_sqlite()
    if chemin.exists():
        return
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    with sqlite3.connect(tmp) as conn:
        if source_base_demo().startswith("migrations"):
            for instruction in _instructions_flyway(dossier_migrations()):
                conn.execute(instruction)
        else:
            conn.executescript(SCRIPT_REPLI.read_text(encoding="utf-8"))
        conn.executescript(SCRIPT_SENSIBLE.read_text(encoding="utf-8"))
    tmp.replace(chemin)


def _autoriser_sqlite(autorisees: set[str]):
    def autoriser(action, arg1, arg2, _db, _trigger):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            return sqlite3.SQLITE_OK if (arg1 or "").lower() in autorisees else sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION:
            return sqlite3.SQLITE_OK if (arg2 or "").lower() in FONCTIONS_SQLITE else sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_DENY  # écriture, PRAGMA, ATTACH, RECURSIVE, transaction...
    return autoriser


def _executer_sqlite(sql: str, autorisees: set[str], params: tuple = ()) -> tuple[list[str], list[tuple]]:
    preparer_base_demo()
    conn = sqlite3.connect(_uri_lecture_seule(), uri=True, timeout=2)
    try:
        conn.execute("PRAGMA query_only = ON")
        conn.set_authorizer(_autoriser_sqlite(autorisees))
        limite = time.monotonic() + delai_ms() / 1000
        conn.set_progress_handler(lambda: 1 if time.monotonic() > limite else 0, 5000)
        cur = conn.execute(sql, params)
        colonnes = [d[0] for d in cur.description or []]
        return colonnes, cur.fetchmany(LIMITE_DURE + 1)
    except sqlite3.DatabaseError as exc:
        message = str(exc)
        if "interrupted" in message:
            raise Refus("delai_depasse", f"Requête interrompue après {delai_ms()} ms.") from None
        if "not authorized" in message or "prohibited" in message:
            raise Refus("refus_moteur", f"Refusé par le moteur SQLite (authorizer) : {message}") from None
        raise Refus("erreur_sql", message[:200]) from None
    finally:
        conn.close()


def _connexion_postgres():
    try:
        import psycopg  # extra « postgres » : uv sync --extra postgres
    except ImportError:
        raise Refus("pilote_absent", "psycopg non installé : uv sync --project labs/mcp --extra postgres") from None
    conn = psycopg.connect(url_base(), autocommit=False, connect_timeout=5,
                           options=f"-c statement_timeout={delai_ms()} -c default_transaction_read_only=on")
    conn.read_only = True
    return conn


def _executer_postgres(sql: str, params: tuple = ()) -> tuple[list[str], list[tuple]]:
    conn = _connexion_postgres()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or None)
            colonnes = [d.name for d in cur.description or []]
            lignes = cur.fetchmany(LIMITE_DURE + 1)
        conn.rollback()
        return colonnes, lignes
    except Refus:
        raise
    except Exception as exc:  # noqa: BLE001 - psycopg.Error et dérivées
        conn.rollback()
        raise Refus("erreur_sql", f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}") from None
    finally:
        conn.close()


def _cellule(v: Any) -> Any:
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime, dt.time)):
        return v.isoformat()
    if isinstance(v, bytes):
        return f"<{len(v)} octets>"
    return v


def executer(sql: str, max_rows: int, params: tuple = (), tables_connues: list[str] | None = None) -> dict:
    """Valide (sauf SQL fixe du serveur, tables_connues renseigné), borne, exécute, enveloppe."""
    autorisees = tables_autorisees()
    d = dialecte()
    if tables_connues is None:
        sql_valide, lues = valider_select(sql, d, autorisees)
    else:
        sql_valide, lues = sql, tables_connues
    sql_borne = f"SELECT * FROM ({sql_valide}) AS resultat_mcp LIMIT {int(max_rows) + 1}"
    if d == "sqlite":
        colonnes, lignes = _executer_sqlite(sql_borne, autorisees, params)
    else:
        colonnes, lignes = _executer_postgres(sql_borne.replace("?", "%s") if params else sql_borne, params)
    tronque = len(lignes) > max_rows
    lignes = [[_cellule(v) for v in ligne] for ligne in lignes[:max_rows]]
    contenu = {"dialect": d, "sql_executed": sql_borne, "columns": colonnes, "rows": lignes,
               "row_count": len(lignes), "truncated": tronque, "tables": lues,
               "sources": [f"db:{url_sans_secret()}#{t}" for t in lues]}
    textes = [str(v) for ligne in lignes for v in ligne if isinstance(v, str)]
    return envelopper(f"db:{d}", contenu, textes)


# --------------------------------------------------------------------------- #
# Outils
# --------------------------------------------------------------------------- #
LECTURE = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}


def _colonnes(table: str) -> list[dict]:
    if dialecte() == "sqlite":
        preparer_base_demo()
        conn = sqlite3.connect(_uri_lecture_seule(), uri=True)
        try:
            # Introspection faite par le serveur (nom de table déjà validé), pas par le modèle.
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        finally:
            conn.close()
        return [{"name": r[1], "type": r[2], "nullable": not r[3]} for r in rows]
    conn = _connexion_postgres()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position", (table,))
            rows = cur.fetchall()
        conn.rollback()
    finally:
        conn.close()
    return [{"name": r[0], "type": r[1], "nullable": r[2] == "YES"} for r in rows]


@mcp.tool(annotations=LECTURE, tags={"lecture"})
def list_tables() -> dict:
    """Liste les tables interrogeables (liste blanche) et leurs colonnes. À appeler avant run_select."""
    tables = {t: [c["name"] for c in _colonnes(t)] for t in sorted(tables_autorisees())}
    return {"dialect": dialecte(), "tables": tables, "max_rows": max_lignes_config(),
            "origine": source_base_demo() if dialecte() == "sqlite" else "base PostgreSQL",
            "sources": [f"db:{url_sans_secret()}"]}


@mcp.tool(annotations=LECTURE, tags={"lecture"})
def describe_table(table: Annotated[str, Field(pattern=r"^[a-z_][a-z0-9_]{0,62}$")]) -> dict:
    """Colonnes, types et nullabilité d'une table autorisée."""
    if table not in tables_autorisees():
        raise Refus("table_non_autorisee", f"Table '{table}' hors liste blanche.")
    return {"table": table, "columns": _colonnes(table), "sources": [f"db:{url_sans_secret()}#{table}"]}


@mcp.tool(annotations=LECTURE, tags={"lecture"})
def run_select(
    sql: Annotated[str, Field(min_length=8, max_length=5000, description="UNE requête SELECT (CTE et UNION acceptés).")],
    max_rows: Annotated[int, Field(ge=1, le=LIMITE_DURE, description="Plafonné par NEOFLOW_DB_MAX_ROWS.")] = 50,
) -> dict:
    """Exécute un SELECT en lecture seule sur les tables autorisées et renvoie au plus max_rows lignes.

    Refusé : écritures, DDL, plusieurs instructions, PRAGMA/ATTACH/COPY, SELECT INTO, FOR UPDATE,
    tables hors liste blanche, fonctions système. Préférer demandes_par_statut quand il suffit.
    """
    return executer(sql, min(max_rows, max_lignes_config()))


@mcp.tool(annotations=LECTURE, tags={"lecture", "metier"})
def demandes_par_statut(
    statut: Literal["BROUILLON", "SOUMISE", "VALIDEE", "REFUSEE", "CLOTUREE"],
    type_demande: Annotated[str | None, Field(pattern=r"^[A-Z_]{3,30}$", description="Ex. CONGES.")] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> dict:
    """Outil MÉTIER : demandes d'un statut donné. Requête FIXE et paramètres liés : le modèle ne fournit pas de SQL."""
    sql = ("SELECT id, type, titre, demandeur, montant, statut, niveau_validation, date_maj "
           "FROM demande WHERE statut = ?")
    params: tuple = (statut,)
    if type_demande:
        sql += " AND type = ?"
        params += (type_demande,)
    return executer(sql + " ORDER BY date_maj DESC", limit, params, tables_connues=["demande"])


if __name__ == "__main__":
    preparer_base_demo()
    journaliser_demarrage(NOM, base=url_sans_secret(), tables=sorted(tables_autorisees()),
                          max_rows=max_lignes_config(),
                          origine=source_base_demo() if dialecte() == "sqlite" else "postgresql")
    mcp.run(show_banner=False)
