package com.neosoft.neoflow.security;

import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import com.neosoft.neoflow.collaborateur.Collaborateur;
import com.neosoft.neoflow.collaborateur.CollaborateurRepository;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

@RestController
@Tag(name = "Utilisateur courant")
public class MoiController {

    private final CollaborateurRepository collaborateurRepository;

    public MoiController(CollaborateurRepository collaborateurRepository) {
        this.collaborateurRepository = collaborateurRepository;
    }

    @GetMapping("/api/moi")
    @Operation(summary = "Login, rôles et département de l'utilisateur connecté (utilisé par le frontend)")
    public UtilisateurCourant moi(Authentication auth) {
        List<String> roles = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .map(role -> role.replaceFirst("^ROLE_", ""))
                .sorted()
                .toList();
        String departement = collaborateurRepository.findById(auth.getName())
                .map(Collaborateur::getDepartement)
                .orElse(null);
        return new UtilisateurCourant(auth.getName(), roles, departement);
    }

    public record UtilisateurCourant(String login, List<String> roles, String departement) {
    }
}
