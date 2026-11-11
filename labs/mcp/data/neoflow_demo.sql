-- Jeu de REPLI du serveur MCP « db » (J06), utilisé seulement si les migrations Flyway du dépôt
-- (backend/src/main/resources/db/migration) sont introuvables. Même schéma que V1__schema.sql,
-- en SQL portable SQLite / PostgreSQL. Données fictives. Aucun secret réel.
-- La table interdite jeton_integration est dans data/jeton_integration.sql (ajoutée dans tous les cas).

CREATE TABLE collaborateur (
    login        VARCHAR(50) PRIMARY KEY,
    nom          VARCHAR(100) NOT NULL,
    departement  VARCHAR(40) NOT NULL,
    date_entree  DATE NOT NULL
);

CREATE TABLE demande (
    id                 INTEGER PRIMARY KEY,
    type               VARCHAR(30) NOT NULL,
    titre              VARCHAR(120) NOT NULL,
    description        VARCHAR(4000),
    demandeur          VARCHAR(50) NOT NULL REFERENCES collaborateur(login),
    montant            NUMERIC(12,2),
    date_debut         DATE NOT NULL,
    date_fin           DATE,
    statut             VARCHAR(20) NOT NULL,
    niveau_validation  INTEGER,
    departement        VARCHAR(40),
    urgent             BOOLEAN NOT NULL DEFAULT FALSE,
    date_creation      TIMESTAMP NOT NULL,
    date_maj           TIMESTAMP NOT NULL,
    motif_refus        VARCHAR(500)
);

CREATE TABLE evenement_demande (
    id           INTEGER PRIMARY KEY,
    demande_id   INTEGER NOT NULL REFERENCES demande(id),
    type         VARCHAR(20) NOT NULL,
    auteur       VARCHAR(50) NOT NULL,
    horodatage   TIMESTAMP NOT NULL,
    commentaire  VARCHAR(500)
);

INSERT INTO collaborateur (login, nom, departement, date_entree) VALUES
    ('alice', 'Alice Martin', 'COMMERCIAL', '2021-03-15'),
    ('bob', 'Bob Durand', 'FINANCE', '2018-09-01'),
    ('admin', 'Admin NeoFlow', 'DSI', '2016-01-04'),
    ('chloe', 'Chloé Bernard', 'DSI', '2025-06-02'),
    ('karim', 'Karim Haddad', 'RH', '2023-11-20');

INSERT INTO demande (id, type, titre, description, demandeur, montant, date_debut, date_fin, statut,
                     niveau_validation, departement, urgent, date_creation, date_maj, motif_refus) VALUES
    (1, 'CONGES', 'Congés de la Toussaint', 'Semaine du 2 novembre', 'alice', NULL, '2026-11-02', '2026-11-06', 'SOUMISE', 1, 'COMMERCIAL', FALSE, '2026-10-10 09:00:00', '2026-10-10 09:05:00', NULL),
    (2, 'NOTE_DE_FRAIS', 'Déplacement client Lyon', 'Train + repas', 'alice', 25.50, '2026-10-08', '2026-10-08', 'VALIDEE', 1, 'COMMERCIAL', FALSE, '2026-10-09 18:20:00', '2026-10-12 08:30:00', NULL),
    (3, 'MATERIEL_IT', 'Écran 27 pouces', 'Poste de développement', 'chloe', 349.00, '2026-10-15', NULL, 'SOUMISE', 2, 'DSI', FALSE, '2026-10-15 10:00:00', '2026-10-15 10:02:00', NULL),
    (4, 'ACHAT', 'Licences outil de test', '10 licences annuelles', 'bob', 5000.00, '2026-10-20', NULL, 'SOUMISE', 3, 'FINANCE', TRUE, '2026-10-20 14:00:00', '2026-10-20 14:10:00', NULL),
    (5, 'GENERIQUE', 'Badge visiteur', 'Visite auditeur', 'karim', NULL, '2026-11-12', NULL, 'BROUILLON', NULL, 'RH', FALSE, '2026-10-29 11:00:00', '2026-10-29 11:00:00', NULL),
    (6, 'FORMATION', 'Formation Kubernetes', '3 jours inter-entreprises', 'chloe', 2000.00, '2026-12-01', '2026-12-03', 'REFUSEE', 2, 'DSI', FALSE, '2026-09-30 09:30:00', '2026-10-02 16:00:00', 'Budget formation épuisé'),
    (7, 'DEPLACEMENT', 'Salon VivaTech', 'Avance demandée', 'alice', 780.00, '2027-06-16', '2027-06-18', 'BROUILLON', NULL, 'COMMERCIAL', FALSE, '2026-10-31 15:45:00', '2026-10-31 15:45:00', NULL),
    (8, 'INCIDENT', 'VPN instable', 'Coupures toutes les 20 minutes', 'karim', NULL, '2026-09-18', NULL, 'CLOTUREE', 1, 'RH', TRUE, '2026-09-18 08:10:00', '2026-09-19 17:00:00', NULL);

INSERT INTO evenement_demande (id, demande_id, type, auteur, horodatage, commentaire) VALUES
    (1, 1, 'CREATION', 'alice', '2026-10-10 09:00:00', NULL),
    (2, 1, 'SOUMISSION', 'alice', '2026-10-10 09:05:00', NULL),
    (3, 2, 'CREATION', 'alice', '2026-10-09 18:20:00', NULL),
    (4, 2, 'SOUMISSION', 'alice', '2026-10-09 18:25:00', NULL),
    (5, 2, 'VALIDATION', 'bob', '2026-10-12 08:30:00', 'Justificatif conforme'),
    (6, 6, 'SOUMISSION', 'chloe', '2026-09-30 09:35:00', NULL),
    (7, 6, 'REFUS', 'bob', '2026-10-02 16:00:00', 'Budget formation épuisé'),
    (8, 8, 'CLOTURE', 'admin', '2026-09-19 17:00:00', 'Incident résolu par l''équipe réseau');
