-- Identité technique en lecture seule pour le serveur MCP « db » (PostgreSQL NeoFlow).
-- À exécuter par le propriétaire de la base, mot de passe passé en variable psql (jamais versionné) :
--
--   psql "postgresql://neoflow@localhost:5432/neoflow" -v ro_password="$NEOFLOW_RO_PASSWORD" \
--        -f labs/mcp/sql/role_lecture_seule_postgres.sql
--
-- Puis, côté OpenCode : NEOFLOW_DB_URL=postgresql://neoflow_ro:<mdp>@localhost:5432/neoflow
-- (variable d'environnement de la session, substituée dans opencode.json par {env:NEOFLOW_DB_URL}).

CREATE ROLE neoflow_ro LOGIN PASSWORD :'ro_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION
    CONNECTION LIMIT 5;

-- Défense en profondeur : même si une écriture passait le filtre du serveur, la session la refuse.
ALTER ROLE neoflow_ro SET default_transaction_read_only = on;
ALTER ROLE neoflow_ro SET statement_timeout = '3s';
ALTER ROLE neoflow_ro SET idle_in_transaction_session_timeout = '10s';

REVOKE ALL ON SCHEMA public FROM neoflow_ro;
GRANT USAGE ON SCHEMA public TO neoflow_ro;

-- Liste blanche : uniquement les tables utiles à l'agent (pas jeton_integration, pas flyway_schema_history).
GRANT SELECT ON demande, evenement_demande, collaborateur TO neoflow_ro;

-- Variante plus stricte : exposer des vues sans colonnes sensibles et ne donner SELECT que sur elles.
-- CREATE VIEW v_demande AS SELECT id, type, titre, statut, niveau_validation, departement, date_maj FROM demande;
-- GRANT SELECT ON v_demande TO neoflow_ro;
