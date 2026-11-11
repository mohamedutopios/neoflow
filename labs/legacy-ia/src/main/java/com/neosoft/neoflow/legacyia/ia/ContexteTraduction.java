package com.neosoft.neoflow.legacyia.ia;

import java.nio.file.Path;

/**
 * Contexte de la tâche TRADUIRE pour le modèle simulé.
 *
 * @param variante       réponse simulée intégrée : {@code naive} (Intl, toLocaleDateString) ou {@code fidele}
 * @param reponseSimulee fichier TypeScript à renvoyer à la place de la variante (peut être {@code null})
 */
public record ContexteTraduction(String variante, Path reponseSimulee) {}
