"""Base en lecture seule : SELECT autorisés, écritures et lectures hors périmètre refusées à chaque barrière."""
from __future__ import annotations

import os

import pytest

import readonly_sql_server as db
from commun.audit import Refus
from conftest import LAB, appeler, dernier_appel, texte

AUTORISEES = {"demande", "evenement_demande", "collaborateur"}


@pytest.mark.parametrize("sql", [
    "SELECT id, titre FROM demande WHERE statut = 'SOUMISE'",
    "select type, count(*) AS n from demande group by type order by n desc",
    "WITH s AS (SELECT * FROM demande WHERE urgent) SELECT s.id, c.departement FROM s JOIN collaborateur c ON c.login = s.demandeur",
    "SELECT d.id, e.type FROM demande d LEFT JOIN evenement_demande e ON e.demande_id = d.id",
    "SELECT * FROM demande /* ; DROP TABLE demande */",
    "SELECT strftime('%Y-%m', date_creation) AS mois, coalesce(sum(montant), 0) FROM demande GROUP BY mois",
])
def test_select_autorises(sql):
    res = appeler(db.mcp, "run_select", {"sql": sql})
    assert not res.is_error, texte(res)
    assert res.structured_content["row_count"] >= 1


@pytest.mark.parametrize("sql, code", [
    ("SELECT id FROM demande; DROP TABLE demande", "multi_instructions"),
    ("COMMIT; DROP SCHEMA public CASCADE", "multi_instructions"),
    ("DELETE FROM demande", "instruction_interdite"),
    ("UPDATE demande SET statut = 'VALIDEE'", "instruction_interdite"),
    ("INSERT INTO demande (id) VALUES (99)", "instruction_interdite"),
    ("DROP TABLE demande", "instruction_interdite"),
    ("PRAGMA table_info(demande)", "instruction_interdite"),
    ("ATTACH DATABASE '/tmp/x.db' AS x", "instruction_interdite"),
    ("VACUUM INTO '/tmp/copie.db'", "instruction_interdite"),
    ("SELECT * INTO copie FROM demande", "instruction_interdite"),
    ("SELECT * FROM jeton_integration", "table_non_autorisee"),
    ("SELECT d.id FROM demande d JOIN jeton_integration j ON 1 = 1", "table_non_autorisee"),
    ("SELECT * FROM (SELECT jeton FROM jeton_integration) t", "table_non_autorisee"),
    ("SELECT 1 UNION SELECT jeton FROM jeton_integration", "table_non_autorisee"),
    ("WITH demande AS (SELECT * FROM jeton_integration) SELECT * FROM demande", "table_non_autorisee"),
    ("SELECT name FROM sqlite_master", "table_non_autorisee"),
    ("SELECT * FROM main.jeton_integration", "table_non_autorisee"),
    ("SELECT load_extension('/tmp/evil')", "fonction_interdite"),
    ("SELECT readfile('/etc/passwd')", "fonction_interdite"),
    ("SELECT * FROM demande WHERE titre = 'x", "sql_illisible"),
])
def test_requetes_refusees_par_l_analyse(sql, code, journal):
    res = appeler(db.mcp, "run_select", {"sql": sql})
    assert res.is_error and f"REFUS [{code}]" in texte(res), texte(res)
    evt = dernier_appel(journal)
    assert evt["decision"] == "refused" and evt["reason"] == code


@pytest.mark.parametrize("sql, code", [
    ("WITH d AS (DELETE FROM demande RETURNING *) SELECT * FROM d", "instruction_interdite"),
    ("SELECT pg_read_file('/etc/passwd')", "fonction_interdite"),
    ("SELECT * FROM pg_catalog.pg_authid", "schema_interdit"),
    ("SELECT * FROM demande FOR UPDATE", "instruction_interdite"),
    ("SELECT * FROM dblink('host=evil', 'select 1') AS t(a int)", "table_fonction"),
    ("SELECT set_config('role', 'postgres', false)", "fonction_interdite"),
    ("COPY demande TO '/tmp/fuite.csv'", "instruction_interdite"),
])
def test_requetes_postgres_refusees_par_l_analyse(sql, code):
    with pytest.raises(Refus) as exc:
        db.valider_select(sql, "postgres", AUTORISEES)
    assert exc.value.code == code


def test_limite_de_lignes_garantie(monkeypatch):
    monkeypatch.setenv("NEOFLOW_DB_MAX_ROWS", "3")
    data = appeler(db.mcp, "run_select", {"sql": "SELECT * FROM evenement_demande LIMIT 1000", "max_rows": 200}).structured_content
    assert data["row_count"] == 3 and data["truncated"] is True
    assert data["sql_executed"].startswith("SELECT * FROM (") and data["sql_executed"].endswith("LIMIT 4")


def test_barriere_moteur_sqlite_si_l_analyse_est_contournee():
    """L'authorizer et mode=ro refusent même un SQL qui n'est pas passé par valider_select."""
    db.preparer_base_demo()
    for sql in ("SELECT jeton FROM jeton_integration", "DELETE FROM demande", "SELECT load_extension('x')",
                "PRAGMA writable_schema = ON"):
        with pytest.raises(Refus) as exc:
            db._executer_sqlite(sql, AUTORISEES)
        assert exc.value.code in {"refus_moteur", "erreur_sql"}, (sql, exc.value)


def test_delai_maximal(monkeypatch):
    monkeypatch.setenv("NEOFLOW_DB_TIMEOUT_MS", "50")
    sql = ("SELECT count(*) FROM evenement_demande a, evenement_demande b, evenement_demande c, evenement_demande d, "
           "evenement_demande e, evenement_demande f, evenement_demande g, evenement_demande h")
    res = appeler(db.mcp, "run_select", {"sql": sql})
    assert res.is_error and "delai_depasse" in texte(res)


def test_outil_metier_parametre():
    data = appeler(db.mcp, "demandes_par_statut", {"statut": "SOUMISE"}).structured_content
    assert {r[0] for r in data["rows"]} == {1, 3, 4}
    assert "?" not in data["sql_executed"].split("WHERE")[0]
    assert appeler(db.mcp, "demandes_par_statut", {"statut": "SOUMISE' OR '1'='1"}).is_error


def test_list_tables_n_expose_que_la_liste_blanche():
    data = appeler(db.mcp, "list_tables").structured_content
    assert set(data["tables"]) == AUTORISEES
    assert appeler(db.mcp, "describe_table", {"table": "jeton_integration"}).is_error


MIGRATIONS_SOCLE = LAB.parent.parent / "backend" / "src" / "main" / "resources" / "db" / "migration"


@pytest.mark.skipif(not any(MIGRATIONS_SOCLE.glob("V*__*.sql")), reason="migrations Flyway du socle absentes")
def test_base_construite_depuis_les_migrations_flyway(monkeypatch, tmp_path):
    """Même schéma et mêmes données que l'application NeoFlow (V1__schema.sql, V2__donnees_demo.sql)."""
    monkeypatch.setenv("NEOFLOW_DB_MIGRATIONS", str(MIGRATIONS_SOCLE))
    monkeypatch.setenv("NEOFLOW_DB_URL", f"sqlite:///{tmp_path / 'flyway.db'}")
    data = appeler(db.mcp, "list_tables").structured_content
    assert data["origine"] == "migrations Flyway du dépôt"
    assert {"nom", "departement", "date_entree"} <= set(data["tables"]["collaborateur"])
    assert {"type", "commentaire", "horodatage"} <= set(data["tables"]["evenement_demande"])
    res = appeler(db.mcp, "run_select", {"sql": "SELECT c.nom, count(*) AS n FROM demande d "
                                                "JOIN collaborateur c ON c.login = d.demandeur GROUP BY c.nom"})
    assert not res.is_error and res.structured_content["row_count"] >= 1
    soumises = appeler(db.mcp, "demandes_par_statut", {"statut": "SOUMISE"}).structured_content
    assert soumises["rows"] and all(r[5] == "SOUMISE" for r in soumises["rows"])
    assert "table_non_autorisee" in texte(appeler(db.mcp, "run_select", {"sql": "SELECT * FROM jeton_integration"}))


@pytest.mark.skipif(not os.environ.get("NEOFLOW_TEST_PG_URL"), reason="NEOFLOW_TEST_PG_URL non défini")
def test_postgres_role_lecture_seule(monkeypatch):
    monkeypatch.setenv("NEOFLOW_DB_URL", os.environ["NEOFLOW_TEST_PG_URL"])
    data = appeler(db.mcp, "run_select", {"sql": "SELECT type, count(*) FROM demande GROUP BY type"}).structured_content
    assert data["dialect"] == "postgres" and data["row_count"] >= 1
    assert appeler(db.mcp, "demandes_par_statut", {"statut": "SOUMISE"}).structured_content["row_count"] == 3
    # Barrière 3 seule (analyse contournée) : la transaction READ ONLY et le rôle refusent.
    for sql in ("DELETE FROM demande", "SELECT jeton FROM jeton_integration"):
        with pytest.raises(Refus) as exc:
            db._executer_postgres(sql)
        assert exc.value.code == "erreur_sql"
