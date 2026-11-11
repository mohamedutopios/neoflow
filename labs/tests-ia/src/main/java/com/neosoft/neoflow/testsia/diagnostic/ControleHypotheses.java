package com.neosoft.neoflow.testsia.diagnostic;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

/**
 * Contrôle déterministe des hypothèses du modèle : une hypothèse qui ne s'appuie sur aucun fait du dossier,
 * qui cite un fait inexistant ou qui n'est pas accompagnée d'un test de reproduction exploitable est rejetée.
 */
public final class ControleHypotheses {

    public record Resultat(List<Hypothese> retenues, List<String> rejets) {
    }

    private static final Set<String> NIVEAUX = Set.of("unitaire", "api", "e2e");

    public Resultat controler(Hypotheses reponse, DossierIncident dossier) {
        // TODO J07-5 (tests : ControleHypothesesTest) — rejeter (motif « Hx rejetée : … ») toute hypothèse :
        //  - sans fait cité dans faitsPour ;
        //  - citant (pour ou contre) un fait absent du dossier : dossier.fait(id).isEmpty() ;
        //  - sans test de reproduction exploitable (classe, méthode, assertion non vides) ou de niveau inconnu (NIVEAUX) ;
        //  - de vraisemblance hors de 1..5.
        // Retenues : triées par vraisemblance décroissante, 3 au plus.
        throw new UnsupportedOperationException("TODO J07-5 : ControleHypotheses.controler");
    }

    private static boolean vide(String s) {
        return s == null || s.isBlank();
    }
}
