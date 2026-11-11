package com.neosoft.neoflow.testsia.modele;

/** Tokens consommés par un appel (ou cumulés), tels que rapportés par l'API ({@code usage}). */
public record Consommation(long entree, long sortie, long lectureCache, long ecritureCache) {

    public static final Consommation NULLE = new Consommation(0, 0, 0, 0);

    public Consommation plus(Consommation autre) {
        return new Consommation(entree + autre.entree, sortie + autre.sortie,
                lectureCache + autre.lectureCache, ecritureCache + autre.ecritureCache);
    }
}
