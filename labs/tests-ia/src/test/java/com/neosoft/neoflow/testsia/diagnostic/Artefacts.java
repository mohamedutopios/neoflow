package com.neosoft.neoflow.testsia.diagnostic;

import java.net.URISyntaxException;
import java.nio.file.Path;

/** Artefacts réels capturés sur le socle NeoFlow avec la régression J07 (copies de demos/artefacts). */
final class Artefacts {

    static final String TRACE_ID = "29748b40f264a4af3249b063849c81f8";

    private Artefacts() {
    }

    static Path ressource(String nom) {
        try {
            return Path.of(Artefacts.class.getResource("/" + nom).toURI());
        } catch (URISyntaxException e) {
            throw new IllegalStateException(e);
        }
    }

    static Path logs() {
        return ressource("incident/backend-ecs.log");
    }

    static Path trace() {
        return ressource("incident/trace-29748b40.json");
    }
}
