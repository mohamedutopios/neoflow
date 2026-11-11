package com.neosoft.neoflow.testsia.modele;

/** Réponse désérialisée et consommation associée. */
public record ReponseModele<T>(T contenu, Consommation consommation) {
}
