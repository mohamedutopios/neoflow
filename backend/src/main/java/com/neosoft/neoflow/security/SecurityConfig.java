package com.neosoft.neoflow.security;

import java.util.List;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.boot.actuate.info.InfoEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

/**
 * Authentification HTTP Basic (comptes en mémoire) et autorisations par rôle.
 * Rôles : DEMANDEUR (créer, modifier, soumettre), VALIDEUR (valider, refuser), ADMIN (clôturer).
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
                // API sans état : identifiants transmis à chaque requête, pas de session ni de cookie
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        // supervision : sondes publiques ; tout autre endpoint Actuator réservé à ADMIN
                        .requestMatchers(EndpointRequest.to(HealthEndpoint.class, InfoEndpoint.class)).permitAll()
                        .requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("ADMIN")
                        .requestMatchers("/v3/api-docs/**", "/swagger-ui/**", "/swagger-ui.html", "/error").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/demandes").hasRole("DEMANDEUR")
                        .requestMatchers(HttpMethod.PUT, "/api/demandes/*").hasRole("DEMANDEUR")
                        .requestMatchers(HttpMethod.POST, "/api/demandes/*/soumettre").hasRole("DEMANDEUR")
                        .requestMatchers(HttpMethod.POST, "/api/demandes/*/valider", "/api/demandes/*/refuser")
                                .hasRole("VALIDEUR")
                        .requestMatchers(HttpMethod.POST, "/api/demandes/*/cloturer").hasRole("ADMIN")
                        .requestMatchers("/api/**").authenticated()
                        .anyRequest().denyAll());
        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService(SecuriteProperties proprietes) {
        List<UserDetails> comptes = proprietes.utilisateurs().stream()
                .map(u -> User.withUsername(u.login())
                        .password(u.motDePasse())
                        .roles(u.roles().toArray(String[]::new))
                        .build())
                .toList();
        return new InMemoryUserDetailsManager(comptes);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
