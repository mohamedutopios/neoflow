package com.neosoft.neoflow.testsia.diagnostic;

import java.util.List;
import java.util.Optional;

/** Faits extraits de façon déterministe : seule matière transmise au modèle. */
public record DossierIncident(String traceId, List<Fait> faits) {

    public Optional<Fait> fait(String id) {
        return faits.stream().filter(f -> f.id().equals(id)).findFirst();
    }

    public String versTexte() {
        StringBuilder sb = new StringBuilder("traceId : ").append(traceId).append('\n');
        faits.forEach(f -> sb.append(f.id()).append(" — ").append(f.description()).append(" [source : ")
                .append(f.source()).append("]\n"));
        return sb.toString();
    }
}
