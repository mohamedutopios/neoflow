# FAQ des développeurs NeoFlow

Questions récurrentes posées sur le canal de l'équipe, avec la réponse validée par le tech lead.

## Pourquoi ma requête renvoie-t-elle 409 ?

La demande n'est pas dans un statut qui autorise l'action. Le circuit est
`BROUILLON -> SOUMISE -> VALIDEE | REFUSEE`, puis `VALIDEE -> CLOTUREE`. Valider une demande encore en
brouillon, ou clôturer une demande refusée, lève `TransitionInvalideException`, traduite en 409 au format
ProblemDetail par le gestionnaire global d'exceptions.

## Pourquoi ma requête renvoie-t-elle 422 ?

Une règle métier a refusé la demande. Les règles implémentent `RegleMetierDemande` ; leurs messages
d'erreur sont renvoyés dans la réponse 422. Corriger la demande, pas la règle.

## Quel compte utiliser pour tester la validation ?

`bob` a le rôle VALIDEUR. `alice` est DEMANDEUR (création, modification, soumission) et `admin` est ADMIN
(clôture). Les mots de passe de démonstration sont dans la configuration du profil de développement : ne
jamais les réutiliser ailleurs.

## Comment ajouter les règles de ma variante ?

Créer un bean Spring qui implémente `RegleMetierDemande` pour votre `TypeDemande` : `type()` renvoie le type
traité, `verifier(Demande)` renvoie la liste des erreurs (vide si la demande est conforme). Le registre des
règles collecte automatiquement les beans ; aucun enregistrement manuel n'est nécessaire.

## Quelle est la première page de la liste des demandes ?

La pagination de l'API commence à 0 : `GET /api/demandes?page=0&size=20` renvoie la première page, avec
les filtres facultatifs `statut` et `type`. Le frontend envoie la même convention.

## Comment retrouver une requête en erreur dans les traces ?

Les logs de la console sont au format ECS et portent le `traceId` de la requête. Copier le `traceId` dans
Jaeger (http://localhost:16686) pour voir le span en erreur et son exception.

## Comment lancer le backend sans Docker ?

`make backend-h2` démarre l'API sur le port 8080 avec une base H2 en mémoire. Le frontend se lance avec
`make frontend` (Vite, port 5173, proxy `/api` vers le backend).
