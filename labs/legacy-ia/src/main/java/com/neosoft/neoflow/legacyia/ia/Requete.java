package com.neosoft.neoflow.legacyia.ia;

/**
 * Requête envoyée au modèle.
 *
 * @param tache       tâche demandée (sert au journal et au modèle simulé)
 * @param systeme     consignes stables (mises en cache côté API)
 * @param utilisateur faits et code numéroté propres à la requête
 * @param contexte    objets Java d'origine ({@code Faits}, impact...) : lus par le modèle simulé, ignorés par Claude
 */
public record Requete(Tache tache, String systeme, String utilisateur, Object contexte) {

    /** Tâches du lab. */
    public enum Tache { EXPLIQUER, IMPACT, DOCUMENTER, TRADUIRE }
}
