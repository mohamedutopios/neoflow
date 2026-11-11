package com.neosoft.neoflow.testsia.diagnostic;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class LecteursTest {

    @Test
    void lecteurEcs_formatImbriqueDeSpringBoot35() {
        List<EvenementLog> logs = new LecteurLogsEcs().lire(Artefacts.logs());

        EvenementLog erreur = logs.stream().filter(l -> Artefacts.TRACE_ID.equals(l.traceId())).filter(EvenementLog::estErreur)
                .findFirst().orElseThrow();
        assertThat(erreur.logger()).isEqualTo("com.neosoft.neoflow.common.GlobalExceptionHandler");
        assertThat(erreur.typeErreur()).isEqualTo("java.lang.NullPointerException");
        assertThat(erreur.spanId()).isEqualTo("756f4834b04cecb5");
        assertThat(erreur.pile()).element(1).asString()
                .isEqualTo("at com.neosoft.neoflow.validation.CircuitValidationService.calculerNiveau(CircuitValidationService.java:31)");
    }

    @Test
    void lecteurEcs_formatAPointsDeSpringBoot34_etLignesNonJsonIgnorees(@TempDir Path dossier) throws IOException {
        Path f = dossier.resolve("ancien.log");
        Files.writeString(f, """
                  .   ____          _            __ _ _
                {"@timestamp":"2026-11-04T19:15:30.098Z","log.level":"ERROR","log.logger":"x.Y","message":"Boum","traceId":"abc","error.type":"java.lang.IllegalStateException","error.stack_trace":"java.lang.IllegalStateException\\n\\tat com.neosoft.A.b(A.java:3)"}
                """);

        List<EvenementLog> logs = new LecteurLogsEcs().lire(f);

        assertThat(logs).singleElement().satisfies(l -> {
            assertThat(l.niveau()).isEqualTo("ERROR");
            assertThat(l.typeErreur()).isEqualTo("java.lang.IllegalStateException");
            assertThat(l.pile()).containsExactly("java.lang.IllegalStateException", "at com.neosoft.A.b(A.java:3)");
        });
    }

    @Test
    void lecteurJaeger_reconstruitLArbreDesSpans() {
        List<SpanTrace> spans = new LecteurTraceJaeger().lire(Artefacts.trace());

        assertThat(spans).hasSize(6);
        SpanTrace racine = spans.stream().filter(SpanTrace::estRacine).findFirst().orElseThrow();
        assertThat(racine.operation()).isEqualTo("http post /api/demandes/{id}/soumettre");
        assertThat(racine.tag("status")).isEqualTo("500");
        assertThat(spans).filteredOn(s -> !s.estRacine()).extracting(SpanTrace::parentId).doesNotContainNull();
    }
}
