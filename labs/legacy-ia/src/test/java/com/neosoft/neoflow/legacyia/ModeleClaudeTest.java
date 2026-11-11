package com.neosoft.neoflow.legacyia;

import com.neosoft.neoflow.legacyia.ia.ModeleClaude;
import com.neosoft.neoflow.legacyia.ia.Reponses.Explication;
import com.neosoft.neoflow.legacyia.ia.Requete;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/** Construction de la requête Claude sans appel réseau (aucune clé n'est lue). */
@DisplayName("Paramètres envoyés à Claude")
class ModeleClaudeTest {

    @Test
    void modeleSystemeEnCacheSortieStructureeEtRepli() {
        var params = ModeleClaude.parametres("claude-sonnet-5-5", true,
                new Requete(Requete.Tache.EXPLIQUER, "consignes", "faits", null), Explication.class);
        String json = params.rawParams()._body().toString();

        assertThat(ModeleClaude.MODELE_PAR_DEFAUT).isEqualTo("claude-sonnet-5-5");
        assertThat(params.rawParams().model().asString()).isEqualTo("claude-sonnet-5-5");
        assertThat(params.rawParams().maxTokens()).isEqualTo(16_000L);
        assertThat(params.rawParams().outputConfig()).isPresent();
        assertThat(json).contains("CacheControlEphemeral")          // consignes système mises en cache
                .contains("affirmations", "testPropose", "citations");  // schéma JSON dérivé du record Explication
        assertThat(params.rawParams()._additionalBodyProperties()).containsKey("fallbacks");
        assertThat(params.rawParams()._headers().values("anthropic-beta")).contains("server-side-fallback-2026-07-01");
    }

    @Test
    void repliDesactivable() {
        var params = ModeleClaude.parametres("claude-haiku-5-5", false,
                new Requete(Requete.Tache.DOCUMENTER, "consignes", "faits", null), Explication.class);
        assertThat(params.rawParams()._additionalBodyProperties()).doesNotContainKey("fallbacks");
    }
}
