package com.neosoft.neoflow.testsia.generateur;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonPropertyDescription;

/** Sortie structurée attendue du modèle pour la génération de tests. */
public record PropositionTests(
        @JsonPropertyDescription("Tests proposés, un par cas") List<TestPropose> tests,
        @JsonPropertyDescription("Comportements non spécifiés : questions pour l'humain, pas de test inventé") List<String> questions) {
}
