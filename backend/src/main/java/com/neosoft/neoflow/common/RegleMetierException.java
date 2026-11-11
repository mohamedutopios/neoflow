package com.neosoft.neoflow.common;

import java.util.List;

/**
 * Une ou plusieurs règles métier refusent la demande (HTTP 422).
 */
public class RegleMetierException extends RuntimeException {

    private final List<String> erreurs;

    public RegleMetierException(List<String> erreurs) {
        super("Règles métier non respectées : " + String.join(" ; ", erreurs));
        this.erreurs = List.copyOf(erreurs);
    }

    public List<String> getErreurs() {
        return erreurs;
    }
}
