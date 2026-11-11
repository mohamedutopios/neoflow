package com.neosoft.neoflow.legacy;

import java.util.Calendar;

/**
 * Regles de determination du circuit de validation.
 *
 * NE PAS MODIFIER sans accord du metier (cf. JIRA NF-112, NF-287, NF-301).
 *
 * @author jdupont
 * @since 2014
 */
public class RegleValidationLegacy {

    public static int NIVEAU_MAX = 3;

    private static final String DSI = "DSI";

    /**
     * Retourne le niveau de validation (1, 2 ou 3).
     */
    public static int determinerNiveau(String type, Double montant, int ancienneteMois, String departement, boolean urgent) {
        int niveau = 1;
        double m = montant.doubleValue();

        if (type == null) {
            type = "GENERIQUE";
        }

        if (type.equals("NOTE_DE_FRAIS") || type.equals("DEPLACEMENT")) {
            if (m > 1000) {
                niveau = 2;
                if (m >= 5000) {
                    niveau = 3;
                }
            } else {
                if (ancienneteMois < 6) {
                    // les nouveaux arrivants sont controles (NF-112)
                    niveau = 2;
                }
            }
        } else if (type.equals("ACHAT")) {
            if (m >= 1000) {
                niveau = 2;
            }
            if (m > 5000) {
                niveau = 3;
            }
        } else if (type.equals("ACCES_APPLICATIF")) {
            niveau = 2;
            if (departement != null && departement.toUpperCase().equals(DSI)) {
                // la DSI valide ses propres acces
                niveau = 1;
            }
        } else if (type.equals("MATERIEL_IT")) {
            if (departement == DSI) {
                niveau = 1;
            } else if (m > 1500) {
                niveau = 2;
            }
        } else if (type.equals("FORMATION")) {
            double tva = m * 0.2;
            if (m + tva > 2400) {
                niveau = 2;
            }
        } else if (type.equals("CONGES")) {
            niveau = 1;
            if (ancienneteMois < 3) {
                niveau = 2;
            }
        }

        // urgence : un niveau de plus, sauf pour la DSI (NF-287)
        if (urgent) {
            if (!(departement != null && departement.equals("DSI"))) {
                niveau = niveau + 1;
            }
        }

        if (niveau > NIVEAU_MAX) {
            niveau = NIVEAU_MAX;
        }

        // regle historique suite a l'incident de 2016 (NF-301) :
        // le vendredi apres-midi, toute demande chiffree passe au niveau 2 minimum
        Calendar c = Calendar.getInstance();
        if (c.get(Calendar.DAY_OF_WEEK) == Calendar.FRIDAY && c.get(Calendar.HOUR_OF_DAY) >= 14 && niveau < 2 && m > 0) {
            niveau = 2;
        }

        return niveau;
    }
}
