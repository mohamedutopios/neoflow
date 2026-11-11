package com.neosoft.neoflow.testsia.diagnostic;

import java.util.List;
import java.util.Map;

/** Un span d'un export Jaeger, avec ses tags et les noms de ses événements (logs du span). */
public record SpanTrace(String traceId, String spanId, String parentId, String operation, long debutMicros,
        long dureeMicros, Map<String, String> tags, List<String> evenements) {

    public boolean estRacine() {
        return parentId == null;
    }

    public String tag(String cle) {
        return tags.get(cle);
    }
}
