package com.neosoft.neoflow.legacyia.ia;

import com.anthropic.client.AnthropicClient;
import com.anthropic.client.okhttp.AnthropicOkHttpClient;
import com.anthropic.core.JsonValue;
import com.anthropic.models.messages.CacheControlEphemeral;
import com.anthropic.models.messages.MessageCreateParams;
import com.anthropic.models.messages.StopReason;
import com.anthropic.models.messages.StructuredMessage;
import com.anthropic.models.messages.StructuredMessageCreateParams;
import com.anthropic.models.messages.TextBlockParam;

import java.util.List;
import java.util.Objects;

/**
 * Implémentation Claude (SDK Java officiel {@code com.anthropic:anthropic-java}).
 *
 * <ul>
 *   <li>sortie structurée : {@code outputConfig(Classe.class)} dérive le schéma JSON du record attendu ;</li>
 *   <li>consignes système en cache ({@code cache_control} éphémère) : elles sont identiques d'un appel à l'autre ;</li>
 *   <li>repli serveur en cas de refus des classifieurs de sécurité ({@code fallbacks: "default"}), désactivable ;</li>
 *   <li>clé lue dans {@code ANTHROPIC_API_KEY} par {@code fromEnv()}, jamais écrite dans le code.</li>
 * </ul>
 */
public final class ModeleClaude implements ModeleLangage {

    /** Modèle par défaut de la formation (choix de modèles de la formation) ; surchargeable par {@code --modele}. */
    public static final String MODELE_PAR_DEFAUT = "claude-sonnet-5-5";
    static final String BETA_REPLI = "server-side-fallback-2026-07-01";
    static final long MAX_TOKENS = 16_000L;

    private final AnthropicClient client;
    private final String modele;
    private final boolean repli;
    private final Journal journal;

    public ModeleClaude(String modele, boolean repli, Journal journal) {
        this.client = AnthropicOkHttpClient.fromEnv();
        this.modele = Objects.requireNonNull(modele);
        this.repli = repli;
        this.journal = journal;
    }

    @Override
    public String nom() {
        return modele;
    }

    @Override
    public <T> T generer(Requete requete, Class<T> typeReponse) {
        StructuredMessage<T> message = client.messages().create(parametres(modele, repli, requete, typeReponse));
        journal.consigner(requete.tache().name(), modele, message.usage().inputTokens(), message.usage().outputTokens(),
                message.usage().cacheReadInputTokens().orElse(0L),
                message.stopReason().map(StopReason::toString).orElse("inconnu"));
        if (message.stopReason().filter(StopReason.REFUSAL::equals).isPresent()) {
            throw new IllegalStateException("Le modèle a refusé la requête " + requete.tache());
        }
        if (message.stopReason().filter(StopReason.MAX_TOKENS::equals).isPresent()) {
            throw new IllegalStateException("Réponse tronquée (max_tokens atteint) pour " + requete.tache());
        }
        return message.content().stream().flatMap(bloc -> bloc.text().stream()).findFirst()
                .map(texte -> texte.text())
                .orElseThrow(() -> new IllegalStateException("Aucune réponse structurée pour " + requete.tache()));
    }

    /** Paramètres de la requête, construits sans appel réseau (testés unitairement). */
    public static <T> StructuredMessageCreateParams<T> parametres(String modele, boolean repli, Requete requete,
                                                           Class<T> typeReponse) {
        MessageCreateParams.Builder builder = MessageCreateParams.builder()
                .model(modele)
                .maxTokens(MAX_TOKENS)
                .systemOfTextBlockParams(List.of(TextBlockParam.builder()
                        .text(requete.systeme())
                        .cacheControl(CacheControlEphemeral.builder().build())
                        .build()));
        if (repli) {
            builder.putAdditionalHeader("anthropic-beta", BETA_REPLI)
                    .putAdditionalBodyProperty("fallbacks", JsonValue.from("default"));
        }
        return builder.outputConfig(typeReponse)
                .addUserMessage(requete.utilisateur())
                .build();
    }
}
