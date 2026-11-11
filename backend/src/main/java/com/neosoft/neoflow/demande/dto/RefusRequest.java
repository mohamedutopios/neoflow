package com.neosoft.neoflow.demande.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record RefusRequest(
        @NotBlank(message = "Le motif de refus est obligatoire") @Size(max = 500) String motif) {
}
