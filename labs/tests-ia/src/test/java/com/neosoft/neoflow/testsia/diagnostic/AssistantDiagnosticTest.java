package com.neosoft.neoflow.testsia.diagnostic;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

import com.neosoft.neoflow.testsia.commun.Journal;
import com.neosoft.neoflow.testsia.modele.ModeleSimule;

/** Diagnostic complet hors ligne : artefacts réels, réponses simulées (src/main/resources/offline/diagnostic.json). */
class AssistantDiagnosticTest {

    @Test
    void retientLHypotheseSourcee_rejetteLHallucination_etJointLeCode() {
        ModeleSimule modele = ModeleSimule.depuisRessource("offline/diagnostic.json");
        AssistantDiagnostic assistant = new AssistantDiagnostic(modele, "com.neosoft", Journal.desactive());

        RapportDiagnostic rapport = assistant.diagnostiquer(Artefacts.logs(), Artefacts.trace(), null, Artefacts.ressource("sources"));

        assertThat(rapport.hypotheses()).first().satisfies(h -> {
            assertThat(h.id()).isEqualTo("H1");
            assertThat(h.test().niveau()).isEqualTo("unitaire");
        });
        assertThat(rapport.rejets()).singleElement().asString().contains("H3", "F9");
        String envoye = modele.demandesRecues().get(0).utilisateur();
        assertThat(envoye).contains("=== DOSSIER ===", Artefacts.TRACE_ID, "=== EXTRAIT DE CODE",
                ">> 31:", "d.getMontant().doubleValue()");
        assertThat(rapport.versMarkdown()).contains("Tests de reproduction proposés", "CircuitValidationServiceTest");
    }
}
