package com.neosoft.neoflow.testsia.generateur;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;

import org.junit.jupiter.api.Test;

class AnalyseurTautologiesTest {

    private final AnalyseurTautologies analyseur = new AnalyseurTautologies();
    private static final Set<String> METHODES = Set.of("calculerNiveau", "ancienneteMois");

    private static String classe(String corps) {
        return """
                package com.neosoft.neoflow.validation;
                import static org.assertj.core.api.Assertions.assertThat;
                import static org.junit.jupiter.api.Assertions.*;
                import static org.mockito.Mockito.mock;
                import org.junit.jupiter.api.Test;
                class XTest {
                    %s
                }
                """.formatted(corps);
    }

    private java.util.List<String> analyser(String corps) {
        return analyseur.analyser(classe(corps), "CircuitValidationService", METHODES);
    }

    @Test
    void testUtile_aucunMotif() {
        assertThat(analyser("@Test void t() { assertThat(circuit.calculerNiveau(d, 24)).isEqualTo(1); }")).isEmpty();
    }

    @Test
    void sansAssertion_estRejete() {
        assertThat(analyser("@Test void t() { circuit.calculerNiveau(d, 24); }"))
                .singleElement().asString().contains("aucune assertion");
    }

    @Test
    void assertionConstante_estRejetee() {
        assertThat(analyser("@Test void t() { circuit.calculerNiveau(d, 24); assertTrue(true); }"))
                .anySatisfy(m -> assertThat(m).contains("assertion constante"));
    }

    @Test
    void expressionCompareeAElleMeme_estRejetee() {
        assertThat(analyser("@Test void t() { assertThat(circuit.calculerNiveau(d, 24)).isEqualTo(circuit.calculerNiveau(d, 24)); }"))
                .anySatisfy(m -> assertThat(m).contains("comparée à elle-même"));
    }

    @Test
    void exceptionAvalee_estRejetee() {
        assertThat(analyser("@Test void t() { try { circuit.calculerNiveau(d, 24); } catch (Exception e) { } assertThat(d).isNotNull(); }"))
                .anySatisfy(m -> assertThat(m).contains("exception avalée"));
    }

    @Test
    void classeTesteeMockee_estRejetee() {
        assertThat(analyser("@Test void t() { CircuitValidationService c = mock(CircuitValidationService.class); assertThat(c.calculerNiveau(d, 1)).isEqualTo(0); }"))
                .anySatisfy(m -> assertThat(m).contains("est mockée"));
    }

    @Test
    void oracleRecalculeParLeLegacy_viaUneVariable_estRejete() {
        assertThat(analyser("""
                @Test void t() {
                    int attendu = RegleValidationLegacy.determinerNiveau("GENERIQUE", 0.0, 24, "RH", false);
                    assertThat(circuit.calculerNiveau(d, 24)).isEqualTo(attendu);
                }"""))
                .anySatisfy(m -> assertThat(m).contains("oracle recalculé"));
    }

    @Test
    void assertionsSeulementFaibles_sontRejetees() {
        assertThat(analyser("@Test void t() { assertThat(circuit.calculerNiveau(d, 24)).isNotNull(); }"))
                .anySatisfy(m -> assertThat(m).contains("trop faibles"));
    }

    @Test
    void attenduRenvoyeParUnStub_estRejete() {
        assertThat(analyser("""
                @Test void t() {
                    when(mapper.versResponse(any())).thenReturn(reponse);
                    assertThat(service.creer(requete, "alice")).isEqualTo(reponse);
                }"""))
                .anySatisfy(m -> assertThat(m).contains("renvoie un stub"));
    }

    @Test
    void exceptionAttendue_estUneVraieAssertion() {
        assertThat(analyser("@Test void t() { org.assertj.core.api.Assertions.assertThatThrownBy(() -> Pagination.index(-1)).isInstanceOf(IllegalArgumentException.class).hasMessageContaining(\"négative\"); }"))
                .isEmpty();
    }
}
