# NF-402 — Dématérialiser les notes de frais

| Champ | Valeur |
|---|---|
| Identifiant | NF-402 |
| Type de demande | `NOTE_DE_FRAIS` |
| Nature | Évolution |
| Rapporteur | Julien Roche, contrôleur de gestion |
| Priorité | Haute |
| Créé le | 2026-10-09 |
| Version cible | NeoFlow 1.1 |
| Statut | À analyser |

## User story

En tant que collaborateur, je veux déclarer mes frais professionnels dans NeoFlow afin d'être remboursé sans remplir de formulaire papier.

## Description (telle que reçue)

Bonjour,

Nous recevons encore environ 600 notes de frais papier par mois, avec les tickets agrafés. La saisie en comptabilité prend deux jours par mois et les erreurs sont fréquentes.

Ce que nous voulons :

1. Une note de frais regroupe plusieurs dépenses (repas, hôtel, transport, kilomètres, divers).
2. Chaque dépense est remboursée selon notre barème. Le barème est déjà dans l'application (le calcul de l'ancien intranet a été repris) : ne surtout pas y toucher, il a été validé par la direction financière.
3. Le justificatif est obligatoire pour toutes les dépenses, sans exception : c'est une exigence de nos commissaires aux comptes.
4. Les dépenses trop anciennes ne sont pas remboursées (plus de trois mois).
5. Le remboursement doit être exact au centime près : les collaborateurs vérifient et nous avons des réclamations dès qu'il manque quelques centimes.
6. Une même dépense ne doit pas pouvoir être remboursée deux fois.

L'écran doit être ergonomique, et utilisable sur mobile si possible, car les commerciaux saisissent souvent leurs frais entre deux rendez-vous.

Nos commerciaux vont régulièrement à Genève et à Londres pour les clients grands comptes.

Cordialement,
Julien Roche

## Pièces jointes

- `bareme_frais_2023.pdf` (non joint au ticket, disponible auprès du contrôle de gestion).

## Commentaires

**Nadia Ferhat, comptable fournisseurs — 2026-10-12**

> Pour les petites dépenses comme le parking ou les péages, on ne demande jamais le justificatif, ce serait ingérable pour tout le monde. Il faudrait garder cette souplesse.

**Julien Roche — 2026-10-12**

> Noté.
