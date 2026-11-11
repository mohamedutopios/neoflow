package com.neosoft.neoflow.testsia.generateur;

import java.util.List;

/** Résultat de la vérification d'un test proposé, avec les motifs (renvoyés au modèle en cas de rejet). */
public record VerdictTest(TestPropose test, Statut statut, List<String> motifs, int tour) {

    public boolean rejete() {
        return statut == Statut.REJETE_TAUTOLOGIE || statut == Statut.REJETE_COMPILATION || statut == Statut.REJETE_STRUCTURE;
    }
}
