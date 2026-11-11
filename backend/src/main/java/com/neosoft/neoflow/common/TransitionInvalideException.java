package com.neosoft.neoflow.common;

import com.neosoft.neoflow.demande.StatutDemande;

/**
 * Action incompatible avec le statut courant de la demande (HTTP 409).
 */
public class TransitionInvalideException extends RuntimeException {

    public TransitionInvalideException(Long demandeId, StatutDemande actuel, StatutDemande cible) {
        super("Transition interdite pour la demande " + demandeId + " : " + actuel + " -> " + cible);
    }

    public TransitionInvalideException(String message) {
        super(message);
    }
}
