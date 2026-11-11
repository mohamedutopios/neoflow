package com.neosoft.neoflow.testsia.diagnostic;

import com.fasterxml.jackson.annotation.JsonPropertyDescription;

/** Le plus petit test qui confirmerait l'hypothèse (rouge avant correctif, vert après). */
public record TestReproduction(
        @JsonPropertyDescription("unitaire, api ou e2e") String niveau,
        @JsonPropertyDescription("Classe de test proposée") String classe,
        @JsonPropertyDescription("Nom de la méthode de test, qui décrit le comportement attendu") String methode,
        @JsonPropertyDescription("Assertion exacte attendue, avec la valeur littérale") String assertion) {
}
