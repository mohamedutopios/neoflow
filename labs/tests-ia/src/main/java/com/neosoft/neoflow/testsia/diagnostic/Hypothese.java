package com.neosoft.neoflow.testsia.diagnostic;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonPropertyDescription;

/** Hypothèse de cause racine, sourcée par des faits du dossier et accompagnée d'un test de reproduction. */
public record Hypothese(
        @JsonPropertyDescription("H1, H2 ou H3") String id,
        @JsonPropertyDescription("Cause supposée, précise (classe, méthode, ligne si connue)") String cause,
        @JsonPropertyDescription("Vraisemblance de 1 (faible) à 5 (forte)") int vraisemblance,
        @JsonPropertyDescription("Identifiants des faits du dossier qui la soutiennent (F1, F2…)") List<String> faitsPour,
        @JsonPropertyDescription("Identifiants des faits qui la contredisent") List<String> faitsContre,
        @JsonPropertyDescription("Observation qui réfuterait l'hypothèse") String refutation,
        TestReproduction test) {
}
