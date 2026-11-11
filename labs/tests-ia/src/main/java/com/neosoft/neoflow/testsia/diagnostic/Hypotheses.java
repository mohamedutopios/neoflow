package com.neosoft.neoflow.testsia.diagnostic;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonPropertyDescription;

/** Sortie structurée attendue du modèle pour le diagnostic. */
public record Hypotheses(
        @JsonPropertyDescription("Trois hypothèses au plus, de la plus à la moins vraisemblable") List<Hypothese> hypotheses,
        @JsonPropertyDescription("Ce qui reste inconnu et la commande ou l'artefact qui le lèverait") List<String> inconnues) {
}
