package com.neosoft.neoflow.demande.dto;

import java.time.LocalDateTime;

import com.neosoft.neoflow.demande.TypeEvenement;

public record EvenementResponse(
        Long id,
        TypeEvenement type,
        String auteur,
        LocalDateTime horodatage,
        String commentaire) {
}
