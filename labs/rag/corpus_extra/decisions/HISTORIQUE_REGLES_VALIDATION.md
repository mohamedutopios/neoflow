# Historique des règles du circuit de validation

Note de synthèse reconstituée à partir des tickets JIRA du projet NF (espace « NeoFlow ») et des
commentaires du code legacy `RegleValidationLegacy`. Elle explique **pourquoi** certaines règles
existent ; le comportement de référence reste celui du code.

## NF-112 — Contrôle des nouveaux arrivants (2015)

- Demande du contrôle de gestion après plusieurs notes de frais refusées a posteriori.
- Règle : pour une note de frais ou un déplacement de 1 000 € ou moins, un collaborateur de moins de
  6 mois d'ancienneté passe au niveau 2 au lieu du niveau 1.
- Au-delà de 1 000 €, la règle du montant s'applique déjà (niveau 2, ou 3 à partir de 5 000 €).
- Porteur métier : contrôle de gestion. Toute modification passe par lui.

## NF-301 — Incident du vendredi 14 octobre 2016

- Constat : plusieurs achats validés le vendredi après-midi au niveau 1, sans second regard,
  dont une commande en double de matériel.
- Décision du comité de direction : le vendredi à partir de 14 h, **toute demande chiffrée** (montant
  strictement positif) est validée au niveau 2 minimum.
- La règle s'appuie sur l'heure du serveur au moment de la soumission. Elle n'a jamais été retirée.

## NF-287 — Demandes urgentes (2017)

- Une demande marquée urgente monte d'un niveau de validation, dans la limite du niveau maximal (3),
  pour qu'un valideur supplémentaire confirme l'urgence.
- Exception : les demandes du département DSI ne montent pas de niveau, la DSI traitant elle-même
  ses urgences d'exploitation.

## Accès applicatifs et matériel IT

- Les demandes d'accès applicatif sont au niveau 2 par défaut ; la DSI valide ses propres accès au
  niveau 1.
- Le matériel IT demandé par la DSI reste au niveau 1 ; pour les autres départements, au-delà de
  1 500 € le niveau 2 s'applique.

## Qui contacter

| Sujet | Référent |
|---|---|
| Règles de validation | Contrôle de gestion |
| Barème de remboursement | Service paie, mise à jour annuelle |
| Habilitations et rôles applicatifs | DSI, équipe sécurité |
