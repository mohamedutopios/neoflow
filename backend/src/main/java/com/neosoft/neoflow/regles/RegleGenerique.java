package com.neosoft.neoflow.regles;

import java.util.ArrayList;
import java.util.List;

import org.springframework.stereotype.Component;

import com.neosoft.neoflow.demande.Demande;
import com.neosoft.neoflow.demande.TypeDemande;

/**
 * Règles communes à toutes les demandes, quel que soit leur type.
 */
@Component
public class RegleGenerique implements RegleMetierDemande {

    @Override
    public TypeDemande type() {
        return TypeDemande.GENERIQUE;
    }

    @Override
    public List<String> verifier(Demande d) {
        List<String> erreurs = new ArrayList<>();
        if (d.getDateDebut() != null && d.getDateFin() != null && d.getDateFin().isBefore(d.getDateDebut())) {
            erreurs.add("La date de fin doit être postérieure ou égale à la date de début");
        }
        if (d.getMontant() != null && d.getMontant().signum() <= 0) {
            erreurs.add("Le montant, s'il est renseigné, doit être strictement positif");
        }
        return erreurs;
    }
}
