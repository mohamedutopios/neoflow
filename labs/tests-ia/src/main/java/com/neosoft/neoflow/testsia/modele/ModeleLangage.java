package com.neosoft.neoflow.testsia.modele;

/**
 * Accès à un modèle de langage, en sortie structurée : la réponse est désérialisée dans {@code format}
 * (un record Java), jamais lue comme du texte libre.
 * <p>
 * Deux implémentations : {@link ModeleClaude} (API Claude, SDK Java Anthropic) et {@link ModeleSimule}
 * (réponses enregistrées, déterministe, mode {@code --offline}).
 */
public interface ModeleLangage {

    <T> ReponseModele<T> demander(DemandeModele demande, Class<T> format);

    /** Nom affiché dans les rapports et le journal (identifiant de modèle ou « simulé »). */
    String nom();
}
