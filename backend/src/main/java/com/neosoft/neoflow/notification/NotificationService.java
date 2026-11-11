package com.neosoft.neoflow.notification;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * Prévient le demandeur des décisions prises sur sa demande.
 * Un échec d'envoi est journalisé mais ne bloque jamais le traitement de la demande.
 */
@Service
public class NotificationService {

    private static final Logger log = LoggerFactory.getLogger(NotificationService.class);

    private final NotificationProperties proprietes;
    private final RestClient client;

    public NotificationService(NotificationProperties proprietes, RestClient.Builder builder) {
        this.proprietes = proprietes;
        this.client = builder
                .baseUrl(proprietes.url() == null ? "" : proprietes.url())
                .defaultHeader("X-Api-Key", proprietes.apiKey() == null ? "" : proprietes.apiKey())
                .build();
    }

    public void notifier(String destinataire, String sujet, String message) {
        if (!proprietes.actif()) {
            log.info("Notification non envoyée (service inactif) : {} -> {}", sujet, destinataire);
            return;
        }
        try {
            client.post()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of(
                            "expediteur", proprietes.expediteur(),
                            "destinataire", destinataire,
                            "sujet", sujet,
                            "message", message))
                    .retrieve()
                    .toBodilessEntity();
        } catch (RestClientException ex) {
            log.warn("Échec de la notification {} -> {} : {}", sujet, destinataire, ex.getMessage());
        }
    }
}
