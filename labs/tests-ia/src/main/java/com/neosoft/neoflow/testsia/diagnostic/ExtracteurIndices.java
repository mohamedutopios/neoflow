package com.neosoft.neoflow.testsia.diagnostic;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * Extraction déterministe des faits d'un incident, AVANT tout appel au modèle : requête en échec, statut
 * du span, logs de la requête, exception, frames applicatives, corrélation log ↔ span, durée dominante.
 * Le modèle ne reçoit que ces faits numérotés : il ne peut citer que ce qui a été observé.
 */
public final class ExtracteurIndices {

    private final String prefixeApplicatif;

    /** @param prefixeApplicatif package du code applicatif (ex. com.neosoft) pour isoler les frames utiles */
    public ExtracteurIndices(String prefixeApplicatif) {
        this.prefixeApplicatif = prefixeApplicatif;
    }

    public DossierIncident extraire(List<EvenementLog> logs, List<SpanTrace> spans, String traceIdDemande) {
        // TODO J07-4 (tests : ExtracteurIndicesTest) — extraction DÉTERMINISTE, sans modèle. Dans l'ordre :
        //  - traceId : traceIdDemande, sinon celui du span racine de la trace exportée, sinon le 1er log ERROR ;
        //  - span racine : « Requête <method> <http.url> : statut <status>, outcome <outcome>, exception=<exception>, durée N ms » ;
        //  - si statut >= 500 sans tag error=true / otel.status_code=ERROR / événement exception : le signaler ;
        //  - chaque log ERROR ou WARN du traceId (logger, message) ;
        //  - l'exception (error.type, error.message) et la première frame applicative (prefixeApplicatif, sans $$SpringCGLIB$$),
        //    « appelée par » la suivante ;
        //  - le span du log d'erreur (corrélation par spanId) ;
        //  - le span enfant le plus long s'il dépasse la moitié de la durée totale.
        // Chaque fait : ajouter(faits, description, source) — source = fichier et champ, ou span et tag.
        throw new UnsupportedOperationException("TODO J07-4 : ExtracteurIndices.extraire");
    }

    private static void ajouter(List<Fait> faits, String description, String source) {
        faits.add(new Fait("F" + (faits.size() + 1), description, source));
    }

    private static int statut(SpanTrace s) {
        try {
            return Integer.parseInt(Objects.requireNonNullElse(s.tag("status"), s.tag("http.status_code")));
        } catch (NumberFormatException | NullPointerException e) {
            return 0;
        }
    }

    private static long ms(long micros) {
        return Math.round(micros / 1000.0);
    }
}
