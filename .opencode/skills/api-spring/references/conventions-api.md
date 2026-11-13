# Conventions API NeoFlow (référence de la skill api-spring)

## Ressources et chemins

| Règle | Exemple NeoFlow |
|---|---|
| Ressource au pluriel, en français, kebab-case | `/api/demandes`, `/api/demandes/{id}/evenements` |
| Action métier = sous-ressource en POST (verbe à l'infinitif) | `POST /api/demandes/{id}/soumettre` |
| Identifiant dans le chemin, filtres en paramètres | `GET /api/demandes?statut=SOUMISE&type=CONGES` |
| Pagination 0-based, `size` borné à 100 | `?page=0&size=20` → `{"content": [...], "page": {"size", "number", "totalElements", "totalPages"}}` |

## Codes HTTP

| Situation | Code | Corps |
|---|---|---|
| Création | 201 + en-tête `Location` | `DemandeResponse` |
| Lecture, modification, action | 200 | `DemandeResponse` |
| JSON invalide, Bean Validation | 400 | ProblemDetail + `errors[]` (champ, message) |
| Non authentifié | 401 | géré par Spring Security |
| Rôle insuffisant ou demande d'un autre utilisateur | 403 | ProblemDetail |
| Ressource absente | 404 | ProblemDetail (`DemandeIntrouvableException`) |
| Transition de statut interdite | 409 | ProblemDetail (`TransitionInvalideException`) |
| Règle métier violée (variante ou GENERIQUE) | 422 | ProblemDetail via `RegleMetierException` (messages de `RegleMetierDemande.verifier`) |

Toujours `application/problem+json` (RFC 9457) via `GlobalExceptionHandler`. Jamais de stack trace,
de requête SQL ni de nom de classe interne dans la réponse.

## DTO et validation

```java
public record DemandeRequest(                                   // existant dans demande/dto/
        @NotNull(message = "Le type est obligatoire") TypeDemande type,
        @NotBlank(message = "Le titre est obligatoire") @Size(max = 120) String titre,
        @Size(max = 4000) String description,
        @Digits(integer = 10, fraction = 2) BigDecimal montant,
        @NotNull(message = "La date de début est obligatoire") LocalDate dateDebut,
        LocalDate dateFin,
        @Size(max = 40) String departement,
        boolean urgent) { }
```
Un nouveau DTO suit le même style : `record`, messages de validation en français, bornes explicites.

- Le demandeur vient de `Authentication#getName()`, jamais du corps de la requête.
- `statut`, `niveauValidation`, dates techniques : calculés par le service, jamais acceptés en entrée.
- Montants en `BigDecimal` (jamais `double`), dates en `LocalDate`.

## Service et transactions

- `@Transactional` sur les méthodes d'écriture du service, `readOnly = true` sur les lectures.
- Chaque changement de statut écrit un `EvenementDemande` (auteur, horodatage, type).
- Les règles passent par `RegleMetierRegistry` : ajouter un bean, ne pas modifier le registre. Les règles
  GENERIQUE s'appliquent à toutes les demandes, en plus de celles du type.
- Tests : `*Test` lancés par `./mvnw test` ; `*IT` (MockMvc, H2, Flyway) seulement par `./mvnw verify`.

## Requêtes

| Besoin | Solution | Interdit |
|---|---|---|
| Filtre simple | méthode dérivée Spring Data | — |
| Recherche texte | `@Query("... where lower(d.titre) like lower(concat('%', :q, '%'))")` | `"... '" + q + "'"` |
| Requête native | `createNativeQuery(sql).setParameter("q", q)` | concaténation, `String.format` |
| Tri dynamique | liste blanche de champs → `Sort.by(champ)` | nom de colonne venant de la requête |

## Logs

Logs structurés (ECS) : identifiant de demande, statut, login. Jamais de mot de passe, de clé,
d'en-tête `Authorization` ni de contenu libre de description.
