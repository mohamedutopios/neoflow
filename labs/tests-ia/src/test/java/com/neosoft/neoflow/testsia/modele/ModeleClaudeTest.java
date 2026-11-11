package com.neosoft.neoflow.testsia.modele;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

import com.anthropic.client.okhttp.AnthropicOkHttpClient;
import com.anthropic.models.messages.MessageCreateParams;
import com.anthropic.models.messages.OutputConfig;
import com.neosoft.neoflow.testsia.generateur.PropositionTests;

/** Construction de la requête Claude, sans aucun appel réseau (clé factice, create() jamais appelé). */
class ModeleClaudeTest {

    private final ModeleClaude modele = new ModeleClaude(
            AnthropicOkHttpClient.builder().apiKey("cle-factice-jamais-utilisee").build(),
            ModeleClaude.MODELE_PAR_DEFAUT, OutputConfig.Effort.MEDIUM, false);

    private final MessageCreateParams params = modele.construireParams(
            new DemandeModele("generation-tests", "CONSIGNES STABLES", "retours du tour 2"), PropositionTests.class).rawParams();

    @Test
    void utiliseLeModeleEtUnPlafondDeSortie() {
        assertThat(params.model().asString()).isEqualTo("claude-sonnet-5-5");
        assertThat(params.maxTokens()).isEqualTo(16_000L);
    }

    @Test
    void metLeMessageSystemeEnCache() {
        var blocs = params.system().orElseThrow().asTextBlockParams();
        assertThat(blocs).singleElement().satisfies(b -> {
            assertThat(b.text()).isEqualTo("CONSIGNES STABLES");
            assertThat(b.cacheControl()).isPresent();
        });
    }

    @Test
    void demandeUneSortieStructureeDeriveeDuRecord() {
        OutputConfig sortie = params.outputConfig().orElseThrow();
        assertThat(sortie.effort()).contains(OutputConfig.Effort.MEDIUM);
        assertThat(sortie.format()).isPresent();
        assertThat(sortie.format().get().toString()).contains("tests", "nomClasse", "source");
    }

    @Test
    void placeLeContenuVariableDansLeMessageUtilisateur() {
        assertThat(params.messages()).singleElement().satisfies(m -> assertThat(m.content().toString()).contains("retours du tour 2"));
    }
}
