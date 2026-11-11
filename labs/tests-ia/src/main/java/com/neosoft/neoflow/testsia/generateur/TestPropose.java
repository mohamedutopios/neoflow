package com.neosoft.neoflow.testsia.generateur;

import com.fasterxml.jackson.annotation.JsonPropertyDescription;

/**
 * Un test proposé par le modèle : une classe JUnit 5 complète, une seule méthode @Test.
 */
public record TestPropose(
        @JsonPropertyDescription("Nom simple de la classe de test, terminé par Test, unique dans la proposition") String nomClasse,
        @JsonPropertyDescription("Identifiant et texte de l'exigence couverte, recopiés de la spécification") String exigence,
        @JsonPropertyDescription("D'où vient la valeur attendue : citation de la spécification (jamais un appel au code testé)") String oracle,
        @JsonPropertyDescription("Code source Java complet de la classe de test (package, imports, classe, une méthode @Test)") String source) {
}
