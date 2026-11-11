# NeoFlow — Dossier d'architecture technique (DAT) v1.4

| | |
|---|---|
| Statut | Validé par le comité d'architecture |
| Rédaction | Cellule études, pôle applications internes |
| Dernière mise à jour | 14 mars 2019 |
| Diffusion | Équipes de développement et d'exploitation |

Ce dossier décrit l'architecture de référence de l'application de gestion des demandes internes NeoFlow.
Il fait foi pour toute évolution : en cas de doute, la règle décrite ici s'applique.

## 1. Vue d'ensemble

NeoFlow permet aux collaborateurs de saisir des demandes (congés, notes de frais, matériel, achats),
de les faire approuver par leur hiérarchie puis de les archiver.

- Socle : Java 8, Spring Boot 2.1, packaging WAR déployé sur Tomcat 8.5.
- Interface : JSF 2.2 avec PrimeFaces 6, rendu côté serveur.
- Base de données : Oracle 12c, schéma `NEOFLOW_OWN`, migrations Liquibase.
- Batch nocturne : archivage des demandes et purge des pièces jointes (Spring Batch).

## 2. Cycle de vie d'une demande

Les statuts sont portés par la colonne `DEM_STATUT` :

```
BROUILLON -> EN_ATTENTE -> APPROUVEE | REJETEE
APPROUVEE -> ARCHIVEE   (batch nocturne, J+30)
```

Une demande `REJETEE` peut être remise en `BROUILLON` par son auteur pour correction et nouvelle soumission.
Toute autre transition est refusée avec une erreur HTTP 400 et un message texte.

## 3. Circuit de validation

Le niveau de validation est calculé **en base de données** par la procédure stockée
`PKG_CIRCUIT.CALCUL_NIVEAU(p_dem_id)`, appelée par `DemandeDAO.soumettre()` au moment de la soumission.

| Montant TTC | Niveau | Valideur |
|---|---|---|
| < 1 500 € | 1 | manager direct (rôle `MANAGER`) |
| de 1 500 € à 10 000 € | 2 | manager puis directeur de département |
| > 10 000 € | 3 | manager, directeur, puis direction financière |

Le type de demande, l'ancienneté et l'urgence ne sont pas pris en compte. Les demandes sans montant
(congés) sont toujours au niveau 1. Les demandes sont validées par le rôle `MANAGER` et archivées par
le rôle `GESTIONNAIRE`.

## 4. Remboursement des frais

Le calcul est réalisé par la procédure `PKG_FRAIS.REMBOURSABLE`. Barème en vigueur :

| Catégorie | Plafond |
|---|---|
| Repas | 19,00 € par repas |
| Hôtel | 90 € par nuit (110 € à l'étranger) |
| Transport | sur justificatif |
| Indemnités kilométriques | 0,52 € / km |

## 5. Interfaces

Les écrans JSF appellent les services Spring directement. Une API REST est exposée pour l'intranet :

```
GET  /rest/demandes?page=1&taille=25     liste paginée, première page = 1
POST /rest/demandes/{id}/approuver       rôle MANAGER
POST /rest/demandes/{id}/rejeter         rôle MANAGER
```

La pagination commence à **1** ; une page 0 renvoie une erreur 400.

## 6. Sécurité

- Authentification par formulaire et session `JSESSIONID`, fédérée avec le CAS de l'entreprise.
- Les rôles `DEMANDEUR`, `MANAGER`, `GESTIONNAIRE` sont lus dans l'annuaire LDAP.
- Les écrans d'administration Tomcat sont accessibles depuis le réseau d'administration uniquement.

## 7. Exploitation

- Journaux applicatifs Log4j 1.2 en fichiers texte (`/var/log/neoflow/neoflow.log`), rotation quotidienne.
- Pas de traçabilité distribuée : en cas d'incident, corréler les horodatages des journaux Tomcat et Oracle.
- Supervision par sonde HTTP sur `/neoflow/ping`.
