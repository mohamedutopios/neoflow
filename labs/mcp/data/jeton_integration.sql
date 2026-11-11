-- Table SENSIBLE fictive, volontairement absente de la liste blanche du serveur MCP « db ».
-- Ajoutée à la base de démonstration (migrations Flyway ou jeu de repli) pour le scénario
-- « lecture interdite » (démo 03, TP 3, TP fil rouge). Valeurs factices, aucun secret réel.
-- Sur une base PostgreSQL de test : psql ... -f labs/mcp/data/jeton_integration.sql

CREATE TABLE jeton_integration (
    id        INTEGER PRIMARY KEY,
    service   VARCHAR(50) NOT NULL,
    jeton     VARCHAR(100) NOT NULL,
    cree_le   TIMESTAMP NOT NULL
);

INSERT INTO jeton_integration (id, service, jeton, cree_le) VALUES
    (1, 'notification', 'FAUX-JETON-DEMO-0000-NE-PAS-UTILISER', '2026-01-10 10:00:00'),
    (2, 'messagerie', 'FAUX-JETON-DEMO-0001-NE-PAS-UTILISER', '2026-02-14 10:00:00');
