package com.neosoft.neoflow.testsia.diagnostic;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/** Lit un export de trace Jaeger (« Trace JSON » de l'UI, ou {@code GET /api/traces/{id}}). */
public final class LecteurTraceJaeger {

    private static final ObjectMapper JSON = new ObjectMapper();

    public List<SpanTrace> lire(Path fichier) {
        try {
            JsonNode racine = JSON.readTree(fichier.toFile());
            List<SpanTrace> spans = new ArrayList<>();
            for (JsonNode trace : racine.path("data")) {
                for (JsonNode s : trace.path("spans")) {
                    Map<String, String> tags = new LinkedHashMap<>();
                    s.path("tags").forEach(t -> tags.put(t.path("key").asText(), t.path("value").asText()));
                    List<String> evenements = new ArrayList<>();
                    s.path("logs").forEach(log -> log.path("fields").forEach(f -> {
                        if ("event".equals(f.path("key").asText())) {
                            evenements.add(f.path("value").asText());
                        }
                    }));
                    String parent = null;
                    for (JsonNode ref : s.path("references")) {
                        if ("CHILD_OF".equals(ref.path("refType").asText())) {
                            parent = ref.path("spanID").asText();
                        }
                    }
                    spans.add(new SpanTrace(s.path("traceID").asText(), s.path("spanID").asText(), parent,
                            s.path("operationName").asText(), s.path("startTime").asLong(), s.path("duration").asLong(),
                            tags, evenements));
                }
            }
            return spans;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
