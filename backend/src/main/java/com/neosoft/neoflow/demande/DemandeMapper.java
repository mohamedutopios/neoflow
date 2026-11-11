package com.neosoft.neoflow.demande;

import org.apache.commons.text.StringEscapeUtils;
import org.springframework.stereotype.Component;

import com.neosoft.neoflow.demande.dto.DemandeRequest;
import com.neosoft.neoflow.demande.dto.DemandeResponse;
import com.neosoft.neoflow.demande.dto.EvenementResponse;

@Component
public class DemandeMapper {

    /**
     * Copie les champs saisis dans l'entité (statut, demandeur et dates techniques exclus).
     */
    public void appliquer(DemandeRequest requete, Demande demande) {
        demande.setType(requete.type());
        demande.setTitre(requete.titre().strip());
        demande.setDescription(requete.description());
        demande.setMontant(requete.montant());
        demande.setDateDebut(requete.dateDebut());
        demande.setDateFin(requete.dateFin());
        demande.setDepartement(normaliserDepartement(requete.departement()));
        demande.setUrgent(requete.urgent());
    }

    public DemandeResponse versResponse(Demande d) {
        return new DemandeResponse(
                d.getId(),
                d.getType(),
                d.getTitre(),
                texte(d.getDescription()),
                d.getDemandeur(),
                d.getMontant(),
                d.getDateDebut(),
                d.getDateFin(),
                d.getStatut(),
                d.getNiveauValidation(),
                d.getDepartement(),
                d.isUrgent(),
                d.getDateCreation(),
                d.getDateMaj(),
                d.getMotifRefus());
    }

    public EvenementResponse versResponse(EvenementDemande e) {
        return new EvenementResponse(e.getId(), e.getType(), e.getAuteur(), e.getHorodatage(), e.getCommentaire());
    }

    /**
     * Les descriptions reprises de l'ancien intranet contiennent des entités HTML (&amp;eacute;, &amp;#39;...).
     */
    private static String texte(String brut) {
        return brut == null ? null : StringEscapeUtils.unescapeHtml4(brut);
    }

    private static String normaliserDepartement(String departement) {
        if (departement == null || departement.isBlank()) {
            return null;
        }
        return departement.strip().toUpperCase();
    }
}
