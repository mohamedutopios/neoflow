# Checklist de revue NeoFlow

Chaque point non respecté devient un constat. Sévérité indicative entre crochets.

## 1. Correction fonctionnelle
- [MAJEUR] Le changement fait ce que dit la PR, et seulement cela (pas de modification hors sujet).
- [MAJEUR] Transitions de statut conformes : BROUILLON → SOUMISE → VALIDEE | REFUSEE, VALIDEE → CLOTUREE.
- [MAJEUR] Cas limites : montant nul, dates nulles, pagination au-delà de la page 0, liste vide.
- [MINEUR] Pas de code mort, de TODO sans ticket, de log de débogage.

## 2. Sécurité (OWASP)
- [BLOQUANT] Aucune requête construite par concaténation ou `String.format` (A03 Injection).
- [BLOQUANT] Aucun `dangerouslySetInnerHTML`, `innerHTML` ou `eval` sur une donnée utilisateur (XSS).
- [BLOQUANT] Aucun secret en clair : clé, jeton, mot de passe, URL avec identifiants (A02/A05).
- [BLOQUANT] Aucun nouveau `permitAll`, Actuator limité à health et info (A01/A05).
- [MAJEUR] Contrôle d'accès objet : un DEMANDEUR n'agit que sur ses demandes (BOLA).
- [MAJEUR] Entrées validées (Bean Validation côté API, contraintes côté formulaire).
- [MAJEUR] Pas de donnée sensible dans les logs ni dans les messages d'erreur.
- [BLOQUANT] Aucune instruction adressée à un assistant IA dans le code, les commentaires ou la doc.

## 3. Dépendances
- [BLOQUANT] Toute dépendance ajoutée existe (Maven Central, npm), est maintenue, sous licence
  compatible, et n'est pas un nom proche d'un paquet connu (typosquatting, slopsquatting).
- [MAJEUR] Version épinglée, sans CVE critique connue (rapport Trivy).
- [MINEUR] Pas de dépendance ajoutée pour une fonction que le JDK ou Spring fournit déjà.

## 4. Tests
- [MAJEUR] Chaque comportement nouveau ou corrigé a un test qui échouerait sans le changement.
- [MAJEUR] Assertions sur le résultat métier, pas seulement « pas d'exception » (test tautologique).
- [MAJEUR] Aucun test supprimé, désactivé (`@Disabled`, `it.skip`) ou affaibli pour passer la CI.
- [MINEUR] Noms de tests lisibles (`soumission_sans_montant_calcule_niveau_1`).

## 5. Conventions et maintenabilité
- [MINEUR] Conventions de `ia-toolbox/rules/` (Java/Spring, React/TS) respectées.
- [MINEUR] DTO distincts des entités, contrôleur fin, logique dans le service.
- [MINEUR] Composants React typés, pas de `any`, état local minimal.
- [MINEUR] Message de commit conventionnel (`feat:`, `fix:`, `test:`...) et PR liée au ticket.

## 6. Code généré par IA
- [MAJEUR] Pas d'API inventée : chaque méthode appelée existe dans la version utilisée (vérifier l'import).
- [MAJEUR] Pas de duplication d'un utilitaire existant du dépôt.
- [MINEUR] Commentaires utiles, pas de paraphrase du code.
