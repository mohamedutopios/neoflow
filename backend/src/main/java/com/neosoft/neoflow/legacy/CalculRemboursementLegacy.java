package com.neosoft.neoflow.legacy;

/**
 * Calcul du montant remboursable d'une depense.
 * Bareme 2023 - a mettre a jour chaque annee (TODO).
 *
 * @author mleroy
 */
public class CalculRemboursementLegacy {

    public static double calculer(String categorie, double montant, int nbNuits, boolean etranger) {
        double plafond = 0;

        if (categorie.equals("REPAS")) {
            plafond = 25.5;
        } else if (categorie.equals("HOTEL")) {
            plafond = 110 * nbNuits;
            if (etranger) {
                plafond = plafond * 1.3;
            }
        } else if (categorie.equals("TRANSPORT")) {
            plafond = 9999; // pas de plafond
        } else if (categorie.equals("KILOMETRIQUE")) {
            plafond = montant; // ici montant = nombre de km
        } else {
            plafond = 50;
        }

        double rembourse = montant > plafond ? plafond : montant;

        if (categorie.equals("KILOMETRIQUE")) {
            rembourse = montant * 0.636; // bareme 5 CV
        }

        if (etranger && !categorie.equals("HOTEL")) {
            rembourse = rembourse * 1.1;
        }

        // arrondi au centime
        rembourse = Math.round(rembourse * 100) / 100;

        return rembourse;
    }
}
