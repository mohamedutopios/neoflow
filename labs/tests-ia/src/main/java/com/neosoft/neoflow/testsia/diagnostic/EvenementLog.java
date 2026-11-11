package com.neosoft.neoflow.testsia.diagnostic;

import java.util.List;

/** Une ligne de log ECS, normalisée (indépendante du format plat ou imbriqué). */
public record EvenementLog(int ligne, String horodatage, String niveau, String logger, String message,
        String traceId, String spanId, String typeErreur, String messageErreur, List<String> pile) {

    public boolean estErreur() {
        return "ERROR".equals(niveau);
    }
}
