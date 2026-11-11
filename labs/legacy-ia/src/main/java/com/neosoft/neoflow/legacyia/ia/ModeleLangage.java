package com.neosoft.neoflow.legacyia.ia;

/**
 * Accès à un modèle de langage qui renvoie une réponse structurée (désérialisée dans {@code typeReponse}).
 * Deux implémentations : {@link ModeleClaude} (API Anthropic) et {@link ModeleSimule} (hors ligne, déterministe).
 */
public interface ModeleLangage {

    <T> T generer(Requete requete, Class<T> typeReponse);

    /** Nom affiché dans les rapports et le journal (ex. {@code claude-sonnet-5-5}, {@code simule}). */
    String nom();
}
