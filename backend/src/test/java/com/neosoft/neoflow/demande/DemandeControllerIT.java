package com.neosoft.neoflow.demande;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.everyItem;
import static org.hamcrest.Matchers.greaterThanOrEqualTo;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.is;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.transaction.annotation.Transactional;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Tests d'intégration de l'API : MockMvc, base H2 (profil test), sécurité HTTP Basic réelle.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
class DemandeControllerIT {

    private static final RequestPostProcessor ALICE = httpBasic("alice", "neoflow");
    private static final RequestPostProcessor BOB = httpBasic("bob", "neoflow");
    private static final RequestPostProcessor ADMIN = httpBasic("admin", "neoflow");

    private static final String NOTE_DE_FRAIS = """
            {"type": "NOTE_DE_FRAIS", "titre": "Taxi gare - client", "description": "Course de taxi",
             "montant": 42.50, "dateDebut": "2026-11-10"}
            """;

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void liste_sansAuthentification_renvoie401() throws Exception {
        mvc.perform(get("/api/demandes")).andExpect(status().isUnauthorized());
    }

    @Test
    void liste_renvoieLaPremierePageAvecSesMetadonnees() throws Exception {
        mvc.perform(get("/api/demandes").param("page", "0").param("size", "5").with(ALICE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content", hasSize(5)))
                .andExpect(jsonPath("$.page.number", is(0)))
                .andExpect(jsonPath("$.page.size", is(5)))
                .andExpect(jsonPath("$.page.totalElements", greaterThanOrEqualTo(12)));
    }

    @Test
    void liste_filtreParStatutEtParType() throws Exception {
        mvc.perform(get("/api/demandes").param("statut", "SOUMISE").param("type", "NOTE_DE_FRAIS").with(BOB))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[*].statut", everyItem(is("SOUMISE"))))
                .andExpect(jsonPath("$.content[*].type", everyItem(is("NOTE_DE_FRAIS"))));
    }

    @Test
    void creation_parUnDemandeur_renvoie201EnBrouillon() throws Exception {
        mvc.perform(post("/api/demandes").with(ALICE).contentType(MediaType.APPLICATION_JSON).content(NOTE_DE_FRAIS))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", containsString("/api/demandes/")))
                .andExpect(jsonPath("$.statut", is("BROUILLON")))
                .andExpect(jsonPath("$.demandeur", is("alice")))
                .andExpect(jsonPath("$.departement", is("COMMERCIAL")));
    }

    @Test
    void creation_parUnValideur_renvoie403() throws Exception {
        mvc.perform(post("/api/demandes").with(BOB).contentType(MediaType.APPLICATION_JSON).content(NOTE_DE_FRAIS))
                .andExpect(status().isForbidden());
    }

    @Test
    void creation_sansTitre_renvoie400AvecLesErreurs() throws Exception {
        mvc.perform(post("/api/demandes").with(ALICE).contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"type": "GENERIQUE", "titre": " ", "dateDebut": "2026-11-10"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.erreurs[0]", containsString("titre")));
    }

    @Test
    void creation_avecUneDateDeFinAvantLaDateDeDebut_renvoie422() throws Exception {
        mvc.perform(post("/api/demandes").with(ALICE).contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"type": "DEPLACEMENT", "titre": "Salon Lille", "montant": 300,
                                 "dateDebut": "2026-11-20", "dateFin": "2026-11-18"}
                                """))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.erreurs[0]", containsString("date de fin")));
    }

    @Test
    void modification_dUnBrouillon_metAJourLaDemande() throws Exception {
        long id = creerNoteDeFrais();

        mvc.perform(put("/api/demandes/{id}", id).with(ALICE).contentType(MediaType.APPLICATION_JSON)
                        .content(NOTE_DE_FRAIS.replace("Taxi gare - client", "Taxi aéroport - client")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.titre", is("Taxi aéroport - client")))
                .andExpect(jsonPath("$.statut", is("BROUILLON")));
    }

    @Test
    void circuitComplet_soumissionValidationCloture_alimenteLHistorique() throws Exception {
        long id = creerNoteDeFrais();

        mvc.perform(post("/api/demandes/{id}/soumettre", id).with(ALICE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.statut", is("SOUMISE")));
        mvc.perform(post("/api/demandes/{id}/valider", id).with(BOB))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.statut", is("VALIDEE")));
        mvc.perform(post("/api/demandes/{id}/cloturer", id).with(ADMIN))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.statut", is("CLOTUREE")));

        mvc.perform(get("/api/demandes/{id}/evenements", id).with(ALICE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[*].type").value(org.hamcrest.Matchers.contains(
                        "CREATION", "SOUMISSION", "VALIDATION", "CLOTURE")))
                .andExpect(jsonPath("$[2].auteur", is("bob")));
    }

    @Test
    void refus_enregistreLeMotif() throws Exception {
        long id = creerNoteDeFrais();
        mvc.perform(post("/api/demandes/{id}/soumettre", id).with(ALICE)).andExpect(status().isOk());

        mvc.perform(post("/api/demandes/{id}/refuser", id).with(BOB).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"motif\": \"Justificatif manquant\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.statut", is("REFUSEE")))
                .andExpect(jsonPath("$.motifRefus", is("Justificatif manquant")));
    }

    @Test
    void refus_sansMotif_renvoie400() throws Exception {
        long id = creerNoteDeFrais();
        mvc.perform(post("/api/demandes/{id}/soumettre", id).with(ALICE)).andExpect(status().isOk());

        mvc.perform(post("/api/demandes/{id}/refuser", id).with(BOB).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"motif\": \"\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void validation_dUnBrouillon_renvoie409EnProblemDetail() throws Exception {
        long id = creerNoteDeFrais();

        mvc.perform(post("/api/demandes/{id}/valider", id).with(BOB))
                .andExpect(status().isConflict())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status", is(409)))
                .andExpect(jsonPath("$.title", is("Transition de statut invalide")))
                .andExpect(jsonPath("$.detail", containsString("BROUILLON -> VALIDEE")));
    }

    @Test
    void cloture_dUneDemandeSoumise_renvoie409() throws Exception {
        long id = creerNoteDeFrais();
        mvc.perform(post("/api/demandes/{id}/soumettre", id).with(ALICE)).andExpect(status().isOk());

        mvc.perform(post("/api/demandes/{id}/cloturer", id).with(ADMIN)).andExpect(status().isConflict());
    }

    @Test
    void modification_dUneDemandeSoumise_renvoie409() throws Exception {
        long id = creerNoteDeFrais();
        mvc.perform(post("/api/demandes/{id}/soumettre", id).with(ALICE)).andExpect(status().isOk());

        mvc.perform(put("/api/demandes/{id}", id).with(ALICE).contentType(MediaType.APPLICATION_JSON)
                        .content(NOTE_DE_FRAIS))
                .andExpect(status().isConflict());
    }

    @Test
    void soumission_parUnValideur_renvoie403() throws Exception {
        long id = creerNoteDeFrais();

        mvc.perform(post("/api/demandes/{id}/soumettre", id).with(BOB)).andExpect(status().isForbidden());
    }

    @Test
    void detail_dUneDemandeInexistante_renvoie404() throws Exception {
        mvc.perform(get("/api/demandes/{id}", 999_999).with(ALICE))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.title", is("Demande introuvable")));
    }

    @Test
    void utilisateurCourant_renvoieLoginEtRoles() throws Exception {
        mvc.perform(get("/api/moi").with(BOB))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.login", is("bob")))
                .andExpect(jsonPath("$.roles[0]", is("VALIDEUR")));
    }

    private long creerNoteDeFrais() throws Exception {
        String json = mvc.perform(post("/api/demandes").with(ALICE).contentType(MediaType.APPLICATION_JSON)
                        .content(NOTE_DE_FRAIS))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        JsonNode demande = objectMapper.readTree(json);
        return demande.get("id").asLong();
    }
}
