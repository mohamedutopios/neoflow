package com.neosoft.neoflow.security;

import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Comptes de démonstration déclarés dans {@code application.yml}.
 */
@ConfigurationProperties(prefix = "neoflow.securite")
public record SecuriteProperties(List<Utilisateur> utilisateurs) {

    public record Utilisateur(String login, String motDePasse, List<String> roles) {
    }
}
