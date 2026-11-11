# NF-408 — Achats hors catalogue

| Champ | Valeur |
|---|---|
| Identifiant | NF-408 |
| Type de demande | `ACHAT` |
| Nature | Évolution |
| Rapporteur | Hélène Dubreuil, directrice des achats |
| Priorité | Haute |
| Créé le | 2026-10-07 |
| Version cible | NeoFlow 1.1 |
| Statut | À analyser |

## User story

En tant que demandeur, je veux faire mes demandes d'achat hors catalogue dans NeoFlow afin qu'elles respectent la politique achats sans aller-retour avec la direction des achats.

## Description (telle que reçue)

Bonjour,

Notre politique achats n'est pas appliquée : des commandes partent sans mise en concurrence, chez des fournisseurs que nous ne connaissons pas, et nous le découvrons à réception de la facture.

Les règles à mettre en place :

- tout achat hors catalogue passe par une demande NeoFlow ;
- le fournisseur doit être référencé chez nous ;
- en dessous de 1 000 €, un devis suffit ; au-delà de 1 000 €, il en faut deux ; au-delà de 5 000 €, trois ;
- les gens ne doivent pas découper leurs achats pour passer sous les seuils ;
- chaque achat est imputé sur un code analytique ;
- certains fournisseurs référencés ont une mauvaise note qualité : il faudrait que le demandeur en soit averti.

Tous les montants de la politique sont exprimés HT.

Le contrôle doit être robuste.

Hélène Dubreuil
Directrice des achats

## Pièces jointes

- Politique achats v3 (non jointe).
- Export du référentiel fournisseurs (à demander à la comptabilité fournisseurs).

## Commentaires

**Julien Roche, contrôle de gestion — 2026-10-08**

> Pour éviter toute discussion avec les demandeurs, les seuils doivent s'apprécier en TTC, comme sur les factures qu'ils reçoivent. C'est ce que tout le monde regarde.

**Hélène Dubreuil — 2026-10-08**

> Je note.
