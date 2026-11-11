package com.neosoft.neoflow.notification;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Paramètres du service de notification (courriel / messagerie interne).
 *
 * @param actif     envoi réel des notifications ; sinon elles sont seulement journalisées
 * @param url       point d'entrée de l'API de notification
 * @param apiKey    clé d'accès à l'API de notification
 * @param expediteur adresse d'expédition
 */
@ConfigurationProperties(prefix = "neoflow.notification")
public record NotificationProperties(boolean actif, String url, String apiKey, String expediteur) {
}
