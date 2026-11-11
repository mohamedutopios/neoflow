package com.neosoft.neoflow.testsia.diagnostic;

/** Un fait extrait des artefacts, citable par son identifiant (F1, F2…) et sourcé. */
public record Fait(String id, String description, String source) {
}
