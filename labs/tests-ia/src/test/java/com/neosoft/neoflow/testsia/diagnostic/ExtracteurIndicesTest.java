package com.neosoft.neoflow.testsia.diagnostic;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/** Extraction déterministe sur les artefacts réels de la régression J07. */
class ExtracteurIndicesTest {

    private final DossierIncident dossier = new ExtracteurIndices("com.neosoft").extraire(
            new LecteurLogsEcs().lire(Artefacts.logs()), new LecteurTraceJaeger().lire(Artefacts.trace()), null);

    @Test
    void retientLeTraceIdDeLaTraceExportee() {
        assertThat(dossier.traceId()).isEqualTo(Artefacts.TRACE_ID);
    }

    @Test
    void decritLaRequeteEnEchecDepuisLeSpanRacine() {
        assertThat(dossier.faits()).anySatisfy(f -> assertThat(f.description())
                .contains("POST /api/demandes/101/soumettre", "statut 500", "exception=NullPointerException"));
    }

    @Test
    void signaleLAbsenceDeStatutOtelErreur() {
        assertThat(dossier.faits()).anySatisfy(f -> assertThat(f.description()).contains("ni statut OTel ERROR"));
    }

    @Test
    void extraitLExceptionEtLaPremiereFrameApplicative() {
        assertThat(dossier.faits()).anySatisfy(f -> assertThat(f.description())
                .startsWith("Exception java.lang.NullPointerException").contains("Demande.getMontant()"));
        assertThat(dossier.faits()).anySatisfy(f -> assertThat(f.description())
                .contains("CircuitValidationService.calculerNiveau(CircuitValidationService.java:31)")
                .contains("DemandeService.soumettre(DemandeService.java:126)")
                .doesNotContain("CGLIB"));
    }

    @Test
    void correleLeLogAuSpanParLeSpanId() {
        assertThat(dossier.faits()).anySatisfy(f -> assertThat(f.description())
                .contains("secured request", "756f4834b04cecb5"));
    }

    @Test
    void chaqueFaitEstNumeroteEtSource() {
        assertThat(dossier.faits()).isNotEmpty().allSatisfy(f -> {
            assertThat(f.id()).matches("F\\d+");
            assertThat(f.source()).isNotBlank();
        });
        assertThat(dossier.faits().get(0).id()).isEqualTo("F1");
    }
}
