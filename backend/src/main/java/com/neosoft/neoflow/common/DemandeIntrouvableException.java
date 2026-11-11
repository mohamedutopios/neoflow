package com.neosoft.neoflow.common;

/**
 * Demande inexistante (HTTP 404).
 */
public class DemandeIntrouvableException extends RuntimeException {

    public DemandeIntrouvableException(Long id) {
        super("Demande " + id + " introuvable");
    }
}
