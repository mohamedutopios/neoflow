package com.neosoft.neoflow.demande;

import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

/**
 * Cycle de vie d'une demande :
 * {@code BROUILLON -> SOUMISE -> VALIDEE | REFUSEE}, puis {@code VALIDEE -> CLOTUREE}.
 * Toute autre transition est refusée (HTTP 409).
 */
public enum StatutDemande {
    BROUILLON,
    SOUMISE,
    VALIDEE,
    REFUSEE,
    CLOTUREE;

    private static final Map<StatutDemande, Set<StatutDemande>> TRANSITIONS = Map.of(
            BROUILLON, EnumSet.of(SOUMISE),
            SOUMISE, EnumSet.of(VALIDEE, REFUSEE),
            VALIDEE, EnumSet.of(CLOTUREE),
            REFUSEE, EnumSet.noneOf(StatutDemande.class),
            CLOTUREE, EnumSet.noneOf(StatutDemande.class));

    public boolean peutPasserA(StatutDemande cible) {
        return TRANSITIONS.get(this).contains(cible);
    }
}
