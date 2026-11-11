# Spécifications

Ce dossier est vide dans le socle. Il reçoit les spécifications produites à partir des tickets de `docs/tickets/`, à partir du J3.

Contenu attendu pour une variante (noms indicatifs) :

| Fichier | Contenu |
|---|---|
| `<TYPE>-questions.md` | Ambiguïtés relevées dans le ticket, questions posées, réponses et décisions humaines datées |
| `<TYPE>-specification.md` | Exigences fonctionnelles (`EF-<TYPE>-NN`) et non fonctionnelles chiffrées (`ENF-<TYPE>-NN`), hors périmètre, hypothèses |
| `<TYPE>.feature` | Scénarios Gherkin ; chaque scénario cite l'exigence qu'il couvre (`@EF-<TYPE>-01`) |
| `<TYPE>-openapi.yaml` | Contrat OpenAPI des routes ajoutées ou modifiées (contract-first) |
| `<TYPE>-plan.md` | Plan technique : tâches, dépendances, ordre, fichiers touchés |
| `<TYPE>-tracabilite.md` | Matrice exigence → scénario → commit → test, mise à jour au J4 et au J7 |

Les décisions d'architecture associées vont dans `docs/adr/`.
