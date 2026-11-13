# Règles de tests — NeoFlow

## Principes

- Toute modification de comportement est livrée avec au moins un test qui échoue sans elle.
- Un test vérifie un comportement observable (statut HTTP, JSON, état persistant, rendu), pas un détail d'implémentation.
- Pas de test tautologique : la valeur attendue n'est jamais recalculée avec le code testé.
- Tests déterministes : pas de dépendance à l'heure courante (utiliser le `Clock` injecté, bean `horloge`), à l'ordre d'exécution ni au réseau. Aucune assertion sur `niveauValidation` (règle legacy dépendante de l'horloge).
- Interdit : supprimer, désactiver (`@Disabled`, `.skip`) ou affaiblir un test existant pour obtenir un build vert. Signaler l'échec.

## Backend (JUnit 5, AssertJ, Mockito, MockMvc)

- Unitaire : `<Classe>Test`, sans contexte Spring, `@ExtendWith(MockitoExtension.class)` et `@Mock`. Lancé par `./mvnw test`.
- Intégration HTTP : `<Classe>IT` avec `@SpringBootTest`, `@AutoConfigureMockMvc`, `@ActiveProfiles("test")`, `@Transactional` sur la classe. Lancé par `./mvnw verify` (failsafe).
- Sécurité réelle : `httpBasic("alice", "neoflow")` (DEMANDEUR), `bob` (VALIDEUR), `admin` (ADMIN), et toujours un cas sans authentification (401) ou avec un mauvais rôle (403).
- Nommage : `action_conditionOuResultat`, comme l'existant (`liste_sansAuthentification_renvoie401`).
- Assertions AssertJ (`assertThat`) ; `jsonPath` pour les corps de réponse.
- Exécution : `cd backend && ./mvnw test -Dtest=<Classe> 2>&1 | grep -E 'Tests run:|FAIL|ERROR|BUILD'` (unitaire ou IT, sans `-q` qui masque `Tests run:`), puis `./mvnw verify`.

## Frontend (Vitest, Testing Library)

- Fichier `*.test.tsx` à côté du composant testé.
- Requêtes par rôle ou libellé (`getByRole`, `getByLabelText`), jamais par classe CSS.
- `src/api/client.ts` simulé avec `vi.mock` ; aucun appel réseau réel.
- Exécution : `cd frontend && npm test` (une passe, `vitest run`).

## Compte rendu attendu

Citer les lignes de résumé (`Tests run: X, Failures: 0, Errors: 0, Skipped: 0` pour les unitaires et pour les IT, ou le résumé Vitest) et le nombre de tests ajoutés.
