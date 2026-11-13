---
name: api-spring
description: Implémente ou modifie un endpoint REST du backend NeoFlow (Spring Boot 3.5, Java 21) - contrôleur, DTO record, Bean Validation, service transactionnel, règle de variante RegleMetierDemande, erreurs ProblemDetail, sécurité par rôle et tests MockMvc. Utiliser quand on demande d'ajouter, modifier ou corriger une API, un endpoint, une route /api/demandes ou une règle métier côté backend. Ne pas utiliser pour le frontend React, pour une revue de PR ni pour le module legacy.
license: Usage interne Neosoft (formation NSS+)
compatibility: opencode >= 2.2, NeoFlow socle J02
metadata:
  domaine: backend
  stack: spring-boot-3.5-java-21
  version: "1.0"
---
# API Spring NeoFlow

Compétence d'implémentation d'endpoint pour le backend NeoFlow. Elle complète les Rules
(`AGENTS.md`, `ia-toolbox/rules/java-spring.md`, `ia-toolbox/rules/securite.md`) sans les répéter.

## Procédure

1. **Contrat d'abord.** Lire la spécification ou le ticket cité par l'utilisateur. Lister : méthode,
   chemin, rôle autorisé, champs et contraintes, codes HTTP attendus. S'il manque une information
   bloquante, poser la question au lieu de supposer.
2. **Repérer l'existant** (lecture ciblée, pas tout le dépôt) : `DemandeController`, `DemandeService`,
   `DemandeMapper`, `RegleMetierRegistry`, `common/GlobalExceptionHandler` (409 `TransitionInvalideException`,
   422 `RegleMetierException`, 404 `DemandeIntrouvableException`), `security/SecurityConfig`. Réutiliser, ne pas dupliquer.
3. **Test d'abord.** Écrire le test MockMvc qui échoue, à partir de `templates/ControllerTest.java.tmpl`
   (cas nominal, validation 400, rôle interdit 403, règle métier 422, transition 409).
4. **Implémenter** en suivant `references/conventions-api.md` :
   - DTO `record` avec Bean Validation, jamais l'entité JPA en entrée ou en sortie ;
   - contrôleur fin, logique dans un service `@Transactional` ;
   - règle de variante = bean `RegleMetierDemande` (`templates/RegleMetier.java.tmpl`) ;
   - accès aux données par Spring Data ou JPQL paramétré, jamais par concaténation de chaîne.
5. **Sécurité** : appliquer `references/checklist-securite-api.md` (rôle, propriété de la ressource,
   validation, pas de donnée sensible en réponse ni dans les logs).
6. **Vérifier** en exécutant le script, sans le recopier :
   `bash .opencode/skills/api-spring/scripts/verifier-api.sh <NomDeClasseTest>`
   Il compile, lance le test ciblé et les règles Semgrep NeoFlow sur les fichiers que vous avez modifiés.
   Corriger jusqu'à ce qu'il sorte en 0. Les défauts préexistants hors de ces fichiers ne sont pas de votre ressort.
7. **Rendre compte** : fichiers modifiés, tests ajoutés, sortie résumée du script, points ouverts.

## Critère d'arrêt

Le script de vérification sort en 0 et chaque exigence du contrat est couverte par un test.
Après trois échecs consécutifs sur la même erreur : s'arrêter et exposer le blocage à l'humain.

## Interdits

- Modifier `SecurityConfig` pour ouvrir un chemin en `permitAll` (hors health et info).
- Modifier une migration Flyway existante : créer `V<n+1>__description.sql`.
- Ajouter une dépendance Maven sans le signaler explicitement (nom, version, raison) : l'humain vérifie
  qu'elle existe sur Maven Central et qu'elle n'est pas vulnérable.

## Ressources (chargées à la demande)

- `references/conventions-api.md` : nommage, codes HTTP, ProblemDetail, pagination.
- `references/checklist-securite-api.md` : OWASP API Top 10 appliqué à NeoFlow.
- `templates/ControllerTest.java.tmpl`, `templates/RegleMetier.java.tmpl` : squelettes à adapter.
- `scripts/verifier-api.sh` : vérification déterministe (compilation, test ciblé, Semgrep).
