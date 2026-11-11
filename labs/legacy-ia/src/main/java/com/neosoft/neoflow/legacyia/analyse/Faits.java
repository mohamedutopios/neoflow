package com.neosoft.neoflow.legacyia.analyse;

import java.util.List;

/**
 * Faits calculés de façon déterministe par JavaParser. C'est la seule matière que le modèle reçoit :
 * il explique ces faits, il ne les découvre pas.
 *
 * @param paquetCible  paquet du module analysé (ex. {@code com.neosoft.neoflow.legacy})
 * @param fichiers     fichiers analysés, chemins relatifs à la racine des sources
 * @param methodes     méthodes du module et de ses appelants (transitifs), avec leur complexité
 * @param champs       champs des classes retenues
 * @param appels       appels entre méthodes retenues (appelant → appelé, fichier:ligne de l'appel)
 * @param dependances  dépendances entre classes, déduites des appels
 * @param constats     constats de dette ou de risque dans le module cible
 * @param pointsEntree endpoints HTTP qui atteignent le module
 */
public record Faits(String paquetCible,
                    List<FichierSource> fichiers,
                    List<Methode> methodes,
                    List<Champ> champs,
                    List<Appel> appels,
                    List<Dependance> dependances,
                    List<Constat> constats,
                    List<PointEntree> pointsEntree) {

    /** Fichier source analysé. */
    public record FichierSource(String chemin, int nbLignes) {}

    /**
     * Méthode ou constructeur.
     *
     * @param id        identifiant stable {@code Classe.methode(Type,Type)}
     * @param signature signature lisible {@code methode(Type nom, ...)}
     */
    public record Methode(String id, String classe, String nom, String signature, String fichier,
                          int ligneDebut, int ligneFin, int complexite, boolean publique, boolean statique,
                          boolean cible) {}

    /** Champ de classe. */
    public record Champ(String classe, String nom, String type, String fichier, int ligne,
                        boolean statique, boolean finalise) {}

    /** Appel de {@code appelant} vers {@code appele}, à la ligne {@code ligne} de {@code fichier}. */
    public record Appel(String appelant, String appele, String fichier, int ligne) {}

    /** Dépendance de classe à classe. */
    public record Dependance(String de, String vers, int nbAppels) {}

    /** Constat localisé, avec l'extrait exact de la ligne. */
    public record Constat(TypeConstat type, String fichier, int ligne, String methode, String extrait,
                          String detail) {}

    /** Endpoint HTTP : verbe, chemin et méthode du contrôleur. */
    public record PointEntree(String verbe, String chemin, String methode) {}

    /** Catégories de constats détectés. */
    public enum TypeConstat {
        NOMBRE_MAGIQUE, COMPARAISON_REFERENCE_STRING, HORLOGE_CACHEE, ETAT_STATIQUE_MUTABLE,
        LOCALE_IMPLICITE, DIVISION_ENTIERE
    }
}
