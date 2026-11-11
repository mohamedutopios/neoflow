package com.neosoft.neoflow.testsia.commun;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.neosoft.neoflow.testsia.modele.Consommation;

/**
 * Journal JSONL des outils (une ligne par événement), dans le format commun des labs :
 * {@code {"ts","session","etape","type","outil","entree","sortie_extrait","usage","modele"}}.
 * Relu au J10 pour mesurer tokens et coûts.
 */
public final class Journal {

    private static final ObjectMapper JSON = new ObjectMapper();

    private final Path fichier;
    private final String session;
    private int etape;

    public Journal(Path fichier, String session) {
        this.fichier = fichier;
        this.session = session;
    }

    public static Journal desactive() {
        return new Journal(null, "aucune");
    }

    public synchronized void ecrire(String type, String outil, String entree, String sortieExtrait,
            Consommation usage, String modele) {
        etape++;
        if (fichier == null) {
            return;
        }
        Map<String, Object> ligne = new LinkedHashMap<>();
        ligne.put("ts", Instant.now().toString());
        ligne.put("session", session);
        ligne.put("etape", etape);
        ligne.put("type", type);
        ligne.put("outil", outil);
        ligne.put("entree", extrait(entree));
        ligne.put("sortie_extrait", extrait(sortieExtrait));
        if (usage != null) {
            ligne.put("usage", Map.of("input_tokens", usage.entree(), "output_tokens", usage.sortie(),
                    "cache_read_input_tokens", usage.lectureCache()));
        }
        ligne.put("modele", modele);
        try {
            Files.createDirectories(fichier.toAbsolutePath().getParent());
            Files.writeString(fichier, JSON.writeValueAsString(ligne) + "\n",
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static String extrait(String texte) {
        if (texte == null) {
            return null;
        }
        return texte.length() <= 300 ? texte : texte.substring(0, 300) + "…";
    }
}
