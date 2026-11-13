# Règles Java / Spring Boot — backend NeoFlow

Portée : `backend/` (Java 21, Spring Boot 3.5). Chaque règle doit pouvoir être vérifiée en revue de diff.

## Structure

- Package par fonctionnalité (`demande/`, `regles/`, `validation/`…), pas par couche technique.
- Controller : traduit HTTP vers DTO et délègue au service. Aucune logique métier, aucun accès direct au repository.
- Service : logique métier ; `@Transactional` sur les écritures, `@Transactional(readOnly = true)` sur les lectures.
- DTO de requête et de réponse en `record` dans `dto/`. Jamais d'entité JPA dans une réponse HTTP.
- Injection par constructeur uniquement (pas de `@Autowired` sur un champ).

## API REST

- Préfixe `/api`, ressource au pluriel en français (`/api/demandes`), action métier en sous-ressource (`/api/demandes/{id}/soumettre`).
- Erreurs : lever une exception de `common/`, traduite en `ProblemDetail` par `GlobalExceptionHandler`. Pas de corps d'erreur construit dans le controller.
- Codes : 400 validation, 401 ou 403 sécurité, 404 introuvable, 409 transition invalide, 422 règle métier.
- Entrées validées par Bean Validation (`@Valid`, `@NotBlank`, `@Positive`…) sur les DTO.
- Pagination : `page` commence à 0, `size` borné.
- Tout nouvel endpoint porte `@Operation(summary = "...")` ; le controller porte `@Tag(name = "Demandes")` ou le tag de sa ressource (springdoc).

## Persistance

- Filtres et agrégations en base (méthode dérivée, `Specification` comme `DemandeRepository.avecFiltres`, JPQL, projection). Interdit : `findAll()` suivi d'un filtre ou d'un comptage en mémoire.
- Montants en `BigDecimal`, jamais `double` ni `float`. Dates en `LocalDate`, horodatages en `LocalDateTime` obtenus via le `Clock` injecté (bean `horloge`), jamais `LocalDateTime.now()` sans horloge.
- Évolution de schéma : nouvelle migration Flyway, jamais de modification d'une migration existante.

## Style

- Vocabulaire métier en français, aligné sur l'existant (`demandeur`, `motifRefus`, `niveauValidation`).
- Logs SLF4J paramétrés (`log.info("Demande {} soumise", id)`), sans donnée personnelle ni secret. Pas de `System.out`.
- `Optional` uniquement en type de retour.
- Pas de dépendance ajoutée au `pom.xml` sans accord explicite (voir `AGENTS.md`).

## Modèle à suivre

Pour un endpoint de lecture : reprendre la forme de `DemandeController#obtenir` (service, DTO `record`, `@Operation`) et le style de `DemandeControllerIT`.
