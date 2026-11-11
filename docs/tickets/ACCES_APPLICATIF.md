# NF-406 — Demandes d'accès aux applications internes

| Champ | Valeur |
|---|---|
| Identifiant | NF-406 |
| Type de demande | `ACCES_APPLICATIF` |
| Nature | Évolution réglementaire |
| Rapporteur | Thomas Lefèvre, RSSI |
| Priorité | Haute |
| Créé le | 2026-09-29 |
| Version cible | NeoFlow 1.1 |
| Statut | À analyser |

## User story

En tant que responsable de la sécurité, je veux que toute demande d'accès à une application interne passe par NeoFlow afin de pouvoir justifier chaque habilitation lors des audits.

## Description (telle que reçue)

Bonjour,

L'audit ISO 27001 de septembre a relevé une non-conformité majeure : nous sommes incapables de dire qui a autorisé la plupart des accès à la comptabilité et à la paie. Les demandes passent par mail, par téléphone, parfois par un simple message au support.

À partir de la version 1.1, toutes les demandes d'accès passent par NeoFlow :

- la demande précise l'application et le niveau de droits souhaité (lecture, contribution, administration) ;
- le manager valide ;
- pour les droits d'administration, il faut une double validation ;
- personne ne doit pouvoir valider sa propre demande ;
- tous les accès doivent être limités dans le temps, c'est un point clé de la remarque d'audit ;
- un collaborateur ne doit pas cumuler des droits incompatibles (par exemple saisir en comptabilité et en paie) ;
- tout doit être tracé : qui a demandé, qui a validé, quand.

Les managers doivent aussi pouvoir faire la demande pour un membre de leur équipe, notamment pour les nouveaux arrivants.

Le système doit être sécurisé et conforme.

Thomas Lefèvre
RSSI

## Pièces jointes

- Extrait du rapport d'audit (diffusion restreinte, non joint).

## Commentaires

**Karim Haddad, DSI — 2026-09-30**

> Pour les accès en lecture, il ne faut pas imposer de date de fin : les accès en consultation sont permanents, on ne va pas embêter tout le monde avec des renouvellements tous les trois mois.

**Thomas Lefèvre — 2026-10-01**

> On en reparle, mais l'idée est là.
