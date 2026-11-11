# Spécification — Adaptateur du circuit de validation (CircuitValidationService)

Source : socle NeoFlow (docs/architecture/ARCHITECTURE.md et code du module legacy), comportement du module legacy à préserver (J8).

| Id | Exigence |
|---|---|
| CV-01 | Une demande **sans montant** (montant absent) est évaluée comme une demande de montant 0 : `calculerNiveau` ne lève pas d'exception. |
| CV-02 | Une demande GENERIQUE, non urgente, sans montant, d'un collaborateur de 24 mois d'ancienneté obtient le **niveau 1**. |
| CV-03 | Une demande de CONGES (jamais chiffrée), non urgente, d'un collaborateur de 24 mois d'ancienneté obtient le **niveau 1** ; avec moins de 3 mois d'ancienneté, le **niveau 2**. |
| CV-04 | Une demande **urgente** monte d'un niveau, sauf pour le département DSI : GENERIQUE urgente sans montant, département RH → **niveau 2**. |
| CV-05 | Le niveau ne dépasse jamais 3. |
| CV-06 | `ancienneteMois(login)` renvoie le nombre de mois révolus entre la date d'entrée du collaborateur et la date du jour (horloge injectée) ; **0** si le collaborateur est absent du référentiel. |

Hors spécification (ne pas tester sans décision) : règle « vendredi après 14 h » du legacy (dépend de l'horloge système, cible du J8).
