package com.neosoft.neoflow.demande.dto;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

import com.neosoft.neoflow.demande.StatutDemande;
import com.neosoft.neoflow.demande.TypeDemande;

public record DemandeResponse(
        Long id,
        TypeDemande type,
        String titre,
        String description,
        String demandeur,
        BigDecimal montant,
        LocalDate dateDebut,
        LocalDate dateFin,
        StatutDemande statut,
        Integer niveauValidation,
        String departement,
        boolean urgent,
        LocalDateTime dateCreation,
        LocalDateTime dateMaj,
        String motifRefus) {
}
