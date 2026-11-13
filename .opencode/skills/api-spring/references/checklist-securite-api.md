# Checklist sécurité d'un endpoint NeoFlow (OWASP API Security Top 10, édition 2023)

Cocher chaque point avant de déclarer l'endpoint terminé.

| # | Risque OWASP API | Contrôle NeoFlow | Test attendu |
|---|---|---|---|
| API1 | Autorisation au niveau objet (BOLA) | Un DEMANDEUR ne lit et ne modifie que ses demandes (`demandeur == auth.getName()`) | alice ne peut pas lire la demande de bob → 403 ou 404 |
| API2 | Authentification | Aucun nouveau `permitAll` ; HTTP Basic sur toute l'API | appel sans identifiants → 401 |
| API3 | Propriétés exposées ou modifiables | DTO dédié ; `statut`, `niveauValidation`, `demandeur` non modifiables | champ `statut` envoyé dans le corps → ignoré |
| API4 | Consommation de ressources | `size` ≤ 100, longueur des champs bornée, recherche limitée à 50 résultats | `size=10000` → plafonné ou 400 |
| API5 | Autorisation au niveau fonction | `@PreAuthorize("hasRole('VALIDEUR')")` sur valider/refuser, `ADMIN` sur clôturer | alice valide → 403 |
| API6 | Flux métier sensibles | Transitions vérifiées par l'état (BROUILLON → SOUMISE...) | double soumission → 409 |
| API7 | SSRF | Aucun appel HTTP construit à partir d'une URL fournie par l'utilisateur | — |
| API8 | Mauvaise configuration | Actuator limité à health/info ; pas de stack trace dans ProblemDetail | `/actuator/env` sans ADMIN → 401/403/404 |
| API9 | Inventaire | Endpoint documenté dans OpenAPI (`/v3/api-docs`), pas d'endpoint caché de debug | — |
| API10 | Consommation d'API tierces | Réponses du service de notification validées, délai d'expiration configuré | — |

Injection (OWASP Top 10 A03) : requêtes paramétrées uniquement ; la règle Semgrep
`neoflow-requete-native-concatenee` doit rester verte.

Secrets (A02/A05) : aucune valeur sensible dans `application.yml` ; utiliser `${VARIABLE}` et
documenter la variable dans `.env.example`.
