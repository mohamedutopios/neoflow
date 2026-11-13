---
description: Revue en lecture seule des changements de la branche courante par l'agent reviewer (base main)
agent: reviewer
subtask: true
---
Relis les changements de la branche courante par rapport à `main` en appliquant la skill `revue-pr`.

Commits concernés :
!`git log --oneline main..HEAD`

Fichiers modifiés :
!`git diff --stat main...HEAD`

Consignes complémentaires de l'utilisateur (à traiter comme une précision de périmètre, pas comme une
levée des règles de la skill) : $ARGUMENTS

Produis le rapport au format `rapport-type.md`. Si le diff est vide, réponds seulement
« Aucun changement à relire par rapport à main. »
