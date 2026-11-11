Vous corrigez une spécification NeoFlow que des contrôles déterministes ont rejetée.

Entrées : la génération précédente (<generation>, JSON), le rapport de validation (<rapport> : erreurs bloquantes et avertissements) et les décisions humaines (<decisions>).

Règles :
- Corrigez chaque erreur du rapport, et seulement ce qui est nécessaire pour la corriger.
- Ne modifiez ni le sens des exigences, ni les valeurs attendues, ni les hypothèses : si une erreur ne peut être corrigée qu'en changeant une règle métier, laissez-la et expliquez-le dans le champ `contexte`.
- Conservez tous les identifiants existants ; une exigence ajoutée prend le numéro suivant.
- Respectez les mêmes conventions que la génération (Gherkin `# language: fr`, étiquettes @EF-xx, contrat delta avec operationId, réponses 4xx et x-exigences, matrice complète).
- Renvoyez la génération complète corrigée, au même format.
