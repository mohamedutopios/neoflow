# ADR-000 : Fondation technique du socle NeoFlow

**Statut** : Accepté
**Date** : 2026-11-04
**Auteur(s)** : Équipe socle NeoFlow (Neosoft)

## Contexte

Le Groupe Velmora remplace l'outil de demandes de son ancien intranet (2014-2015) par une application web interne, NeoFlow. Le socle doit être compris rapidement par des développeurs Java et TypeScript, testable sur un poste sans infrastructure, observable, et extensible par type de demande sans modifier le cœur. Une partie des règles historiques (circuit de validation, barèmes de remboursement, formatage) existe déjà dans du code ancien, non testé, dont le métier exige de préserver le comportement.

## Options considérées

### Option A : monolithe Spring Boot en couches + SPA React

- Avantages : stack maîtrisée par les équipes ; un seul déployable côté serveur ; tests d'intégration simples (MockMvc, H2).
- Inconvénients : le découpage par type de demande reste logique, pas physique.

### Option B : un service par type de demande

- Avantages : isolation forte des variantes.
- Inconvénients : coût d'infrastructure et de coordination disproportionné pour une application interne ; transactions et audit répartis.

### Option C : réécriture complète du legacy avant toute fonctionnalité

- Avantages : base de code homogène.
- Inconvénients : risque de régression métier élevé sans tests de caractérisation ; délai sans valeur livrée.

## Décision

**Option A** retenue, avec le legacy conservé tel quel derrière un adaptateur.

## Justification

- Monolithe Spring Boot 3.5 / Java 21 en couches (`controller → service → repository`), les services renvoyant des DTO (records). Une SPA React 18 + TypeScript (Vite) consomme l'API par `/api`.
- Cycle de vie porté par l'énumération `StatutDemande` (table des transitions), toute transition invalide étant traduite en 409 ProblemDetail.
- Extension par variante via l'interface `RegleMetierDemande` et le registre `RegleMetierRegistry`. Un nouveau type ne modifie ni le contrôleur ni le service.
- Legacy isolé : `CircuitValidationService` est le seul appelant de `RegleValidationLegacy`. Il protège le legacy d'un montant absent en passant `0.0`.
- Authentification HTTP Basic avec comptes en mémoire : suffisant pour une démonstration, remplaçable par OIDC sans toucher au domaine.
- PostgreSQL en développement, H2 en mode PostgreSQL pour les tests et les postes sans Docker ; schéma géré par Flyway uniquement (`ddl-auto: validate`).
- Observabilité dès le départ : logs ECS portant le `traceId`, traces OpenTelemetry exportées en OTLP vers Jaeger.

## Conséquences

### Positives
- Démarrage en une commande (`make up`, ou `make backend-h2` et `make frontend`).
- Les variantes s'ajoutent par composition (beans de règles, migrations `V3__` et suivantes).
- Une erreur en production se retrouve des logs à la trace par le `traceId`.

### Négatives
- Les comptes en mémoire ne conviennent pas à la production.
- Le legacy reste non testé : toute modification exige d'abord des tests de caractérisation.
- La compatibilité SQL PostgreSQL / H2 limite l'usage de fonctionnalités propres à PostgreSQL dans les migrations.

### Neutres / À surveiller
- Spring Boot 3.5 : deux CVE de Spring Framework 6.2 (non applicables à NeoFlow) ne sont corrigées qu'en Spring Boot 4 ; elles sont acceptées temporairement dans `.trivyignore` et une migration vers Spring Boot 4 est à planifier avant le 2027-03-31.
- Le circuit du socle comporte un seul valideur ; un circuit à plusieurs étapes est une décision d'architecture à part entière.

## Indicateurs de remise en cause

- Plus de trois variantes ont besoin de modifier `StatutDemande` ou les transitions.
- Les contraintes d'authentification d'un client imposent un fournisseur d'identité.
- Le temps de démarrage ou de test dépasse ce qu'accepte la boucle de développement assisté.

## Référence

- `docs/architecture/ARCHITECTURE.md`
- `backend/src/main/java/com/neosoft/neoflow/validation/CircuitValidationService.java`
