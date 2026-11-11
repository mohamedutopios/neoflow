package com.neosoft.neoflow.testsia.modele;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Modèle simulé, déterministe : renvoie, dans l'ordre, des réponses JSON enregistrées par tâche.
 * Sert au mode {@code --offline} (formation sans clé, plan B), aux tests du lab et à rejouer un scénario.
 * <p>
 * Format d'un fichier de réponses : {@code {"<tache>": [ {réponse tour 1}, {réponse tour 2}, ... ]}}.
 */
public final class ModeleSimule implements ModeleLangage {

    private static final ObjectMapper JSON = new ObjectMapper()
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, true);

    private final Map<String, Deque<String>> reponses = new LinkedHashMap<>();
    private final List<DemandeModele> demandesRecues = new ArrayList<>();

    public ModeleSimule repondre(String tache, String json) {
        reponses.computeIfAbsent(tache, t -> new ArrayDeque<>()).add(json);
        return this;
    }

    public static ModeleSimule depuisFichier(Path fichier) {
        try (InputStream in = Files.newInputStream(fichier)) {
            return depuisFlux(in);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    public static ModeleSimule depuisRessource(String chemin) {
        InputStream in = ModeleSimule.class.getClassLoader().getResourceAsStream(chemin);
        if (in == null) {
            throw new IllegalArgumentException("Réponses simulées introuvables : " + chemin);
        }
        try (in) {
            return depuisFlux(in);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static ModeleSimule depuisFlux(InputStream in) throws IOException {
        ModeleSimule modele = new ModeleSimule();
        JsonNode racine = JSON.readTree(in);
        racine.properties().forEach(e -> e.getValue().forEach(r -> modele.repondre(e.getKey(), r.toString())));
        return modele;
    }

    @Override
    public <T> ReponseModele<T> demander(DemandeModele demande, Class<T> format) {
        demandesRecues.add(demande);
        Deque<String> file = reponses.get(demande.tache());
        if (file == null || file.isEmpty()) {
            throw new ModeleException("Plus de réponse simulée pour la tâche « " + demande.tache() + " »");
        }
        try {
            T contenu = JSON.readValue(file.poll(), format);
            long entree = (demande.systeme().length() + demande.utilisateur().length()) / 4;
            return new ReponseModele<>(contenu, new Consommation(entree, 0, 0, 0));
        } catch (IOException e) {
            throw new ModeleException("Réponse simulée non conforme à " + format.getSimpleName(), e);
        }
    }

    /** Demandes reçues, dans l'ordre (utile pour vérifier ce que la boucle renvoie au modèle). */
    public List<DemandeModele> demandesRecues() {
        return List.copyOf(demandesRecues);
    }

    @Override
    public String nom() {
        return "simulé (offline)";
    }
}
