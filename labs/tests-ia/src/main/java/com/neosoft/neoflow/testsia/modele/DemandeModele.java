package com.neosoft.neoflow.testsia.modele;

/**
 * Une demande au modèle.
 *
 * @param tache       clé de la tâche (« generation-tests », « diagnostic ») : journal et réponses simulées
 * @param systeme     consignes stables (mises en cache côté API : ne rien y mettre de variable)
 * @param utilisateur contenu variable de la demande (code, spécification, retours du vérificateur)
 */
public record DemandeModele(String tache, String systeme, String utilisateur) {
}
