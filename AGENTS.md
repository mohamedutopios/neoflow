# AGENTS.md — NeoFlow

Application interne de gestion de demandes : création, soumission, circuit de validation, clôture.
Dépôt unique : `backend/` (Spring Boot 3.5, Java 21, Maven), `frontend/` (React 18, TypeScript, Vite), `e2e/` (Playwright), `labs/` (Python, laboratoires IA), `docs/`.

## Commandes (lancer depuis le dossier indiqué)

Toujours le wrapper `./mvnw`, jamais `mvn`.

| Objectif | Commande |
|---|---|
| Tests unitaires backend (`*Test`) | `cd backend && ./mvnw test` |
| Unitaires + intégration (`*IT`, H2, Flyway) | `cd backend && ./mvnw verify` |
| Un seul test, unitaire ou IT, résumé seulement | voir la commande ci-dessous |
| Tests frontend (Vitest, une passe) | `cd frontend && npm test` |
| Lint et typage frontend | `cd frontend && npm run lint && npm run typecheck` |

Test ciblé, avec la ligne `Tests run:` à citer (`-q` la supprime : ne pas l'utiliser quand le résultat doit être cité) :

```bash
cd backend && ./mvnw test -Dtest=DemandeControllerIT 2>&1 | grep -E 'Tests run:|FAIL|ERROR|BUILD'
```

Ordre avant de rendre la main : test ciblé, puis `./mvnw verify` ; côté front `npm run lint`, `npm run typecheck`, `npm test`.
Ne lancer ni `docker compose`, ni le backend, ni les tests E2E : ce sont des commandes longues ou bloquantes, demander à l'utilisateur. Démarrage sans Docker, par l'utilisateur : `cd backend && ./mvnw spring-boot:run -Dspring-boot.run.profiles=dev-h2`.

## Architecture backend (`com.neosoft.neoflow`)

- `demande/` : entité `Demande`, `StatutDemande` (transitions dans l'enum), repository (filtres par `Specification`), service, controller ; DTO en `record` dans `demande/dto/`. Le controller ne porte aucune logique métier.
- Cycle de vie : `BROUILLON → SOUMISE → VALIDEE | REFUSEE`, `VALIDEE → CLOTUREE`. Transition interdite : `TransitionInvalideException`, HTTP 409 en `ProblemDetail` via `common/GlobalExceptionHandler`.
- Règles propres à un type de demande : nouveau bean qui implémente `regles/RegleMetierDemande` (erreurs → HTTP 422). Jamais de `if (type == ...)` dans `DemandeService`.
- `validation/CircuitValidationService` est le seul point d'entrée vers `legacy/`.
- `legacy/` et `frontend/src/legacy/` : ne pas modifier. Leurs bizarreries sont des comportements à préserver.
- Base : migrations Flyway `backend/src/main/resources/db/migration/V<n>__<description>.sql`. Ne jamais modifier une migration existante, en ajouter une.
- Profils : `dev` (défaut, PostgreSQL sous Docker), `dev-h2` (sans Docker), `test` (H2, utilisé par les tests).
- Sécurité : HTTP Basic, comptes de démonstration `alice` (DEMANDEUR), `bob` (VALIDEUR), `admin` (ADMIN). Toute nouvelle route en écriture reçoit sa règle de rôle dans `security/SecurityConfig` ; ne jamais en retirer une pour faire passer un test.

## Frontend

- Appels HTTP uniquement via `src/api/client.ts` ; une page par fichier dans `src/pages/`, composants partagés dans `src/components/`.
- Le proxy Vite redirige `/api` vers le backend (8080) : pas d'URL absolue dans le code.

## Interdits

- Aucune nouvelle dépendance Maven ou npm sans accord explicite.
- Ne jamais lire, afficher ni copier `.env`, `*.env.*`, `secrets/` ; aucun secret dans le code, les tests ou les messages.
- Ne pas modifier, désactiver ni supprimer un test existant pour obtenir un build vert : signaler l'échec.
- Pas de `git push`, `git reset --hard`, `git commit --amend` ni `rm -rf`. Les commits sont faits par l'humain après relecture.
- Le socle contient des failles volontaires (F1 à F5, traitées au J2) : les signaler si on les croise, ne pas les corriger sans demande explicite.

## Définition de « terminé »

1. Test ciblé puis `cd backend && ./mvnw verify` verts (ou `npm test`) : citer les lignes `Tests run: ...` des tests unitaires et d'intégration.
2. Diff minimal : aucun reformatage ni renommage hors du périmètre demandé.
3. Réponse finale : fichiers modifiés, commandes lancées avec leur résultat, hypothèses prises, points à vérifier par l'humain.
