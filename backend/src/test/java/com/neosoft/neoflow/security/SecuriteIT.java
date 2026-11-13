package com.neosoft.neoflow.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.greaterThanOrEqualTo;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.transaction.annotation.Transactional;

/**
 * Non-régression sécurité (J02) : F1 injection SQL, F4 secret hors du dépôt, F5 Actuator.
 * Chaque test échoue sur le socle d'origine et passe après correction.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class SecuriteIT {

    private static final RequestPostProcessor ALICE = httpBasic("alice", "neoflow");
    private static final RequestPostProcessor ADMIN = httpBasic("admin", "neoflow");

    @Autowired
    private MockMvc mvc;

    @Value("${neoflow.notification.api-key:}")
    private String cleNotification;

    @Test
    void F1_recherche_nominale_trouve_par_titre() throws Exception {
        mvc.perform(get("/api/demandes/recherche").param("q", "Badge").with(ALICE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()", greaterThanOrEqualTo(1)));
    }

    @ParameterizedTest
    @ValueSource(strings = {"' OR '1'='1' --", "x' UNION SELECT * FROM demande --", "%", "_"})
    void F1_saisie_malveillante_ou_joker_ne_renvoie_rien(String q) throws Exception {
        mvc.perform(get("/api/demandes/recherche").param("q", q).with(ALICE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(0)));
    }

    @Test
    void F4_cle_de_notification_absente_de_la_configuration_versionnee() {
        assertThat(cleNotification).as("la clé doit venir de NEOFLOW_NOTIFICATION_API_KEY").isEmpty();
    }

    @Test
    void F5_health_reste_public() throws Exception {
        mvc.perform(get("/actuator/health")).andExpect(status().isOk());
    }

    @ParameterizedTest
    @ValueSource(strings = {"/actuator/env", "/actuator/configprops", "/actuator/heapdump", "/actuator/metrics"})
    void F5_endpoints_sensibles_refuses_sans_authentification(String chemin) throws Exception {
        mvc.perform(get(chemin)).andExpect(status().isUnauthorized());
    }

    @ParameterizedTest
    @ValueSource(strings = {"/actuator/env", "/actuator/configprops", "/actuator/metrics"})
    void F5_endpoints_sensibles_inaccessibles_a_un_demandeur(String chemin) throws Exception {
        // 403 si l'endpoint est exposé mais réservé à ADMIN, 404 s'il n'est plus exposé : jamais 200.
        mvc.perform(get(chemin).with(ALICE))
                .andExpect(r -> assertThat(r.getResponse().getStatus()).isIn(403, 404));
    }

    @Test
    void F5_metrics_accessible_a_admin() throws Exception {
        mvc.perform(get("/actuator/metrics").with(ADMIN)).andExpect(status().isOk());
    }
}
