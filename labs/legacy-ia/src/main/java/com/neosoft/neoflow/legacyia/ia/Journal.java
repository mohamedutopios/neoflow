package com.neosoft.neoflow.legacyia.ia;

import com.neosoft.neoflow.legacyia.analyse.ExportJson;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/** Journal JSONL des appels au modèle (garde-fou J2 : traçabilité des tokens et des tâches). */
public final class Journal {

    private final Path fichier;

    public Journal(Path fichier) {
        this.fichier = fichier;
    }

    public void consigner(String tache, String modele, long tokensEntree, long tokensSortie, long tokensCacheLus,
                          String issue) {
        Map<String, Object> ligne = new LinkedHashMap<>();
        ligne.put("ts", Instant.now().toString());
        ligne.put("type", "llm");
        ligne.put("tache", tache);
        ligne.put("modele", modele);
        ligne.put("usage", Map.of("input_tokens", tokensEntree, "output_tokens", tokensSortie,
                "cache_read_input_tokens", tokensCacheLus));
        ligne.put("issue", issue);
        try {
            Files.createDirectories(fichier.toAbsolutePath().getParent());
            Files.writeString(fichier, ExportJson.JSON.writeValueAsString(ligne) + System.lineSeparator(),
                    StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
