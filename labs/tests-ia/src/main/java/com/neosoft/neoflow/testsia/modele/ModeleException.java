package com.neosoft.neoflow.testsia.modele;

/** Réponse inexploitable : refus, réponse tronquée, contenu absent ou non conforme au format. */
public class ModeleException extends RuntimeException {

    public ModeleException(String message) {
        super(message);
    }

    public ModeleException(String message, Throwable cause) {
        super(message, cause);
    }
}
