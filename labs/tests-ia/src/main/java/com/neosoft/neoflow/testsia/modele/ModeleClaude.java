package com.neosoft.neoflow.testsia.modele;

import java.util.List;

import com.anthropic.client.AnthropicClient;
import com.anthropic.client.okhttp.AnthropicOkHttpClient;
import com.anthropic.core.JsonSchemaLocalValidation;
import com.anthropic.core.JsonValue;
import com.anthropic.models.messages.CacheControlEphemeral;
import com.anthropic.models.messages.MessageCreateParams;
import com.anthropic.models.messages.OutputConfig;
import com.anthropic.models.messages.StopReason;
import com.anthropic.models.messages.StructuredMessage;
import com.anthropic.models.messages.StructuredMessageCreateParams;
import com.anthropic.models.messages.StructuredOutputConfig;
import com.anthropic.models.messages.StructuredTextBlock;
import com.anthropic.models.messages.TextBlockParam;
import com.anthropic.models.messages.Usage;

/**
 * Modèle Claude via le SDK Java officiel ({@code com.anthropic:anthropic-java}).
 * <ul>
 *   <li>Sortie structurée : le schéma JSON est dérivé du record {@code format} ({@code outputConfig(Class)}),
 *       la réponse est validée et désérialisée par le SDK.</li>
 *   <li>Prompt caching : le message système (consignes stables) porte {@code cache_control} ;
 *       les tours suivants d'une même boucle relisent ce préfixe depuis le cache.</li>
 *   <li>Refus et troncature sont des erreurs explicites, jamais une réponse vide silencieuse.</li>
 * </ul>
 * Clé lue dans {@code ANTHROPIC_API_KEY} (ou profil {@code ant auth login}) ; jamais en dur.
 */
public final class ModeleClaude implements ModeleLangage {

    public static final String MODELE_PAR_DEFAUT = "claude-sonnet-5-5";
    static final long MAX_TOKENS = 16_000L;

    private final AnthropicClient client;
    private final String modele;
    private final OutputConfig.Effort effort;
    private final boolean secoursServeur;

    public ModeleClaude(AnthropicClient client, String modele, OutputConfig.Effort effort, boolean secoursServeur) {
        this.client = client;
        this.modele = modele;
        this.effort = effort;
        this.secoursServeur = secoursServeur;
    }

    /** Client construit depuis l'environnement ; effort « medium » ; repli serveur en cas de refus activé. */
    public static ModeleClaude depuisEnvironnement(String modele) {
        return new ModeleClaude(AnthropicOkHttpClient.fromEnv(), modele, OutputConfig.Effort.MEDIUM, true);
    }

    /** Paramètres de la requête (séparés de l'appel pour être testés sans réseau). */
    public <T> StructuredMessageCreateParams<T> construireParams(DemandeModele demande, Class<T> format) {
        // TODO J07-1 (tests : ModeleClaudeTest) — construire la requête Messages API avec le SDK Java :
        //  - MessageCreateParams.builder() : model(modele), maxTokens(MAX_TOKENS) ;
        //  - message système = demande.systeme() dans un TextBlockParam portant CacheControlEphemeral (prompt caching) :
        //    systemOfTextBlockParams(List.of(TextBlockParam.builder().text(...).cacheControl(...).build())) ;
        //  - message utilisateur = demande.utilisateur() (addUserMessage) ;
        //  - sortie structurée dérivée du record : outputConfig(format), puis
        //    outputConfig(StructuredOutputConfig.<T>builder().effort(effort).format(format, JsonSchemaLocalValidation.YES).build()) ;
        //  - si secoursServeur : putAdditionalHeader("anthropic-beta", "server-side-fallback-2026-07-01")
        //    et putAdditionalBodyProperty("fallbacks", JsonValue.from("default")).
        throw new UnsupportedOperationException("TODO J07-1 : ModeleClaude.construireParams");
    }

    @Override
    public <T> ReponseModele<T> demander(DemandeModele demande, Class<T> format) {
        // TODO J07-1 — appeler client.messages().create(construireParams(demande, format)) ; AUCUN appel réel pendant le TP
        // sans clé : utilisez --offline. Puis :
        //  - stopReason REFUSAL -> ModeleException ; MAX_TOKENS -> ModeleException (réponse tronquée) ;
        //  - contenu = premier bloc texte structuré : message.content().stream().flatMap(b -> b.text().stream())
        //    .map(StructuredTextBlock::text).findFirst() ;
        //  - consommation = consommation(message.usage()).
        throw new UnsupportedOperationException("TODO J07-1 : ModeleClaude.demander");
    }

    static Consommation consommation(Usage usage) {
        return new Consommation(usage.inputTokens(), usage.outputTokens(),
                usage.cacheReadInputTokens().orElse(0L), usage.cacheCreationInputTokens().orElse(0L));
    }

    @Override
    public String nom() {
        return modele;
    }
}
