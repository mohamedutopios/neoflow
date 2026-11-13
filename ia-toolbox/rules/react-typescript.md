# Règles React / TypeScript — frontend NeoFlow

Portée : `frontend/` (React 18, TypeScript strict, Vite, React Router, Vitest et Testing Library).

## Code

- Composants fonctionnels et hooks. Un composant exporté par fichier, nom en PascalCase identique au nom du fichier.
- TypeScript strict : pas de `any` (préférer `unknown` puis une garde de type), pas de `@ts-ignore`, pas de `as` pour faire taire le compilateur.
- Types d'API dans `src/api/`, alignés champ pour champ sur les DTO du backend. Statuts en union littérale :
  `type StatutDemande = 'BROUILLON' | 'SOUMISE' | 'VALIDEE' | 'REFUSEE' | 'CLOTUREE'`.
- Appels HTTP uniquement via `src/api/client.ts`. Chaque écran gère explicitement les états chargement, erreur et liste vide.
- Montants et dates formatés avec `Intl.NumberFormat('fr-FR', …)` et `Intl.DateTimeFormat('fr-FR', …)`. Ne pas étendre `src/legacy/`.
- Ne jamais introduire `dangerouslySetInnerHTML`, `eval` ni stockage de mot de passe dans `localStorage`.
- Accessibilité : éléments natifs (`button`, `a`, `label` associé à chaque champ), pas de `div` cliquable.
- Aucune nouvelle bibliothèque (UI, état, requêtes) sans accord explicite.

## Vérification

- `cd frontend && npm run lint && npm run build` doit passer sans avertissement nouveau.
- Tests : voir `tests.md`.
