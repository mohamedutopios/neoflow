# Décisions d'architecture (ADR)

Une ADR consigne une décision structurante : son contexte, les options étudiées, la décision prise et ses conséquences. Elle est courte (une à deux pages), datée et versionnée avec le code qu'elle concerne.

## Convention

- Fichier `ADR-NNN-titre-court.md`, numéroté sans trou. `ADR-000` est réservée au socle ; vos décisions commencent à `ADR-001`.
- Statut : `Proposé`, puis `Accepté` après relecture par un pair, `Déprécié` ou `Remplacé par ADR-NNN`. On ne réécrit pas une ADR acceptée : on en crée une nouvelle qui la remplace.
- Sections : Contexte, Options considérées, Décision, Justification, Conséquences (positives, négatives, à surveiller), Indicateurs de remise en cause, Référence (ticket, spécification, fichiers).
- Une décision qui touche toutes les variantes (statuts, transitions, sécurité, schéma commun) exige une ADR.
- Le commit qui applique la décision cite l'ADR dans son message.

## Index

| ADR | Titre | Statut |
|---|---|---|
| [ADR-000](ADR-000-fondation-socle.md) | Fondation technique du socle NeoFlow | Accepté |
