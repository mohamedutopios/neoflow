package com.neosoft.neoflow.demande;

/**
 * Types de demande gérés par NeoFlow. Le socle n'implémente que des règles génériques :
 * chaque variante ajoute les règles de son type (voir {@code regles.RegleMetierDemande}).
 */
public enum TypeDemande {
    GENERIQUE,
    CONGES,
    NOTE_DE_FRAIS,
    MATERIEL_IT,
    RESERVATION_SALLE,
    FORMATION,
    ACCES_APPLICATIF,
    DEPLACEMENT,
    ACHAT,
    INCIDENT,
    ONBOARDING
}
