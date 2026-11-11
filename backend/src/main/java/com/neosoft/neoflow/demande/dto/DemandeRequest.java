package com.neosoft.neoflow.demande.dto;

import java.math.BigDecimal;
import java.time.LocalDate;

import com.neosoft.neoflow.demande.TypeDemande;

import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/**
 * Données saisies à la création ou à la modification d'une demande.
 *
 * @param departement département imputé ; s'il est absent, celui du collaborateur est utilisé
 */
public record DemandeRequest(
        @NotNull(message = "Le type est obligatoire") TypeDemande type,
        @NotBlank(message = "Le titre est obligatoire") @Size(max = 120) String titre,
        @Size(max = 4000) String description,
        @Digits(integer = 10, fraction = 2) BigDecimal montant,
        @NotNull(message = "La date de début est obligatoire") LocalDate dateDebut,
        LocalDate dateFin,
        @Size(max = 40) String departement,
        boolean urgent) {
}
