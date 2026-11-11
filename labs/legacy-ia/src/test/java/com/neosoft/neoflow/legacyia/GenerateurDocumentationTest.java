package com.neosoft.neoflow.legacyia;

import com.neosoft.neoflow.legacyia.analyse.AnalyseurLegacy;
import com.neosoft.neoflow.legacyia.analyse.Faits;
import com.neosoft.neoflow.legacyia.doc.GenerateurDocumentation;
import com.neosoft.neoflow.legacyia.doc.GenerateurDocumentation.DocumentationVerifiee;
import com.neosoft.neoflow.legacyia.doc.VerificateurDocumentation;
import com.neosoft.neoflow.legacyia.ia.ModeleSimule;
import com.neosoft.neoflow.legacyia.ia.Reponses.JavadocProposee;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("Documentation générée puis vérifiée")
class GenerateurDocumentationTest {

    static Faits faits;
    static AnalyseurLegacy analyseur;

    @BeforeAll
    static void preparer() {
        analyseur = Fixtures.analyseur();
        faits = analyseur.analyser();
    }

    @Nested
    @DisplayName("Vérificateur de noms et de signatures (TODO 5 du starter)")
    class Verificateur {

        @Test
        void signatureReelleAcceptee() {
            VerificateurDocumentation v = new VerificateurDocumentation(faits, analyseur.code());
            assertThat(v.verifier(new JavadocProposee("RegleValidationLegacy",
                    "determinerNiveau(String type, Double montant, int ancienneteMois, String departement, boolean urgent)",
                    "Compare `departement` à `DSI` ; plafonne à `NIVEAU_MAX`."))).isEmpty();
        }

        @Test
        void signatureInventeeRejetee() {
            VerificateurDocumentation v = new VerificateurDocumentation(faits, analyseur.code());
            assertThat(v.verifier(new JavadocProposee("RegleValidationLegacy", "determinerNiveau(String type)", "x")))
                    .hasValueSatisfying(m -> assertThat(m).startsWith("signature inexistante"));
        }

        @Test
        void nomsInventesDetectes() {
            VerificateurDocumentation v = new VerificateurDocumentation(faits, analyseur.code());
            assertThat(v.nomsInconnus("Voir `RegleValidationLegacy.calculerNiveauDsi()` et `TauxTvaService`."))
                    .containsExactlyInAnyOrder("RegleValidationLegacy.calculerNiveauDsi", "calculerNiveauDsi", "TauxTvaService");
            assertThat(v.nomsInconnus("`RegleValidationLegacy.NIVEAU_MAX`, `montant > 1000`, `Calendar.getInstance()`")).isEmpty();
        }
    }

    @Test
    @DisplayName("hors ligne : signature et noms inventés rejetés, parties calculées présentes")
    void generationSimulee() {
        DocumentationVerifiee doc = new GenerateurDocumentation(new ModeleSimule(analyseur.code(), null), analyseur.code())
                .generer(faits);

        assertThat(doc.rejets()).hasSize(3)
                .anySatisfy(r -> assertThat(r).contains("signature inexistante"))
                .anySatisfy(r -> assertThat(r).contains("calculerNiveauDsi"))
                .anySatisfy(r -> assertThat(r).contains("TauxTvaService"));
        assertThat(doc.javadocs()).extracting(JavadocProposee::classe)
                .containsExactlyInAnyOrder("CalculRemboursementLegacy", "RegleValidationLegacy");
        String readme = GenerateurDocumentation.readme(faits, doc);
        assertThat(readme).contains("```mermaid", "POST | `/api/demandes/{id}/soumettre`", "| COMPARAISON_REFERENCE_STRING |",
                "Éléments rejetés par la vérification", "determinerNiveau(String type, Double montant");
        assertThat(GenerateurDocumentation.javadocs(doc)).contains("/**", " */");
    }
}
