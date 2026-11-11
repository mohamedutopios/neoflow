package com.neosoft.neoflow.testsia.diagnostic;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Lit des logs ECS (une ligne JSON par événement). Accepte les deux formes produites par Spring Boot :
 * champs imbriqués (3.5 : {@code "log":{"level":…}}, {@code "error":{"type":…}}) et champs à points (3.4 :
 * {@code "log.level"}, {@code "error.type"}). Les lignes non JSON (bannière, sortie Maven) sont ignorées.
 */
public final class LecteurLogsEcs {

    private static final ObjectMapper JSON = new ObjectMapper();

    public List<EvenementLog> lire(Path fichier) {
        try {
            List<String> lignes = Files.readAllLines(fichier);
            List<EvenementLog> evenements = new ArrayList<>();
            for (int i = 0; i < lignes.size(); i++) {
                String l = lignes.get(i).strip();
                if (!l.startsWith("{")) {
                    continue;
                }
                JsonNode n = JSON.readTree(l);
                String pile = champ(n, "error", "stack_trace");
                evenements.add(new EvenementLog(i + 1, texte(n.get("@timestamp")), champ(n, "log", "level"),
                        champ(n, "log", "logger"), texte(n.get("message")), texte(n.get("traceId")), texte(n.get("spanId")),
                        champ(n, "error", "type"), champ(n, "error", "message"),
                        pile == null ? List.of() : Arrays.stream(pile.split("\\R")).map(String::strip).toList()));
            }
            return evenements;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    /** Valeur de « parent.enfant », sous forme imbriquée ou à point. */
    private static String champ(JsonNode n, String parent, String enfant) {
        JsonNode imbrique = n.path(parent).path(enfant);
        if (!imbrique.isMissingNode() && !imbrique.isNull()) {
            return imbrique.asText();
        }
        return texte(n.get(parent + "." + enfant));
    }

    private static String texte(JsonNode n) {
        return n == null || n.isNull() ? null : n.asText();
    }
}
