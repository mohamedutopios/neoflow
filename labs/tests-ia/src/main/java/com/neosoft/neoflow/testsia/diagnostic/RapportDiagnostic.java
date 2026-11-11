package com.neosoft.neoflow.testsia.diagnostic;

import java.util.List;

import com.neosoft.neoflow.testsia.modele.Consommation;

/** Rapport de diagnostic : faits, hypothèses retenues avec leur test, rejets, inconnues. */
public record RapportDiagnostic(DossierIncident dossier, List<Hypothese> hypotheses, List<String> rejets,
        List<String> inconnues, String modele, Consommation consommation) {

    public String versMarkdown() {
        StringBuilder sb = new StringBuilder("# Diagnostic assisté — traceId ").append(dossier.traceId()).append("\n\n");
        sb.append("Modèle : ").append(modele).append(" · tokens entrée/sortie : ").append(consommation.entree())
                .append(" / ").append(consommation.sortie()).append("\n\n## Faits extraits (déterministes)\n\n");
        sb.append("| Id | Fait | Source |\n|---|---|---|\n");
        dossier.faits().forEach(f -> sb.append("| ").append(f.id()).append(" | ").append(e(f.description())).append(" | ")
                .append(e(f.source())).append(" |\n"));
        sb.append("\n## Hypothèses retenues\n\n| Id | Cause | Vraisemblance | Pour | Contre | Réfutée si |\n|---|---|---|---|---|---|\n");
        hypotheses.forEach(h -> sb.append("| ").append(h.id()).append(" | ").append(e(h.cause())).append(" | ")
                .append(h.vraisemblance()).append("/5 | ").append(String.join(", ", h.faitsPour())).append(" | ")
                .append(h.faitsContre() == null ? "" : String.join(", ", h.faitsContre())).append(" | ")
                .append(e(h.refutation())).append(" |\n"));
        sb.append("\n## Tests de reproduction proposés (à écrire et à voir rouges avant tout correctif)\n\n");
        hypotheses.forEach(h -> sb.append("- ").append(h.id()).append(" — ").append(h.test().niveau()).append(" : `")
                .append(h.test().classe()).append('.').append(h.test().methode()).append("` → ")
                .append(h.test().assertion()).append('\n'));
        if (!rejets.isEmpty()) {
            sb.append("\n## Hypothèses rejetées par le contrôle\n\n");
            rejets.forEach(r -> sb.append("- ").append(r).append('\n'));
        }
        if (inconnues != null && !inconnues.isEmpty()) {
            sb.append("\n## Inconnues\n\n");
            inconnues.forEach(i -> sb.append("- ").append(i).append('\n'));
        }
        sb.append("\n> Ces hypothèses ne valent rien sans preuve : la vérification est humaine, par le test de reproduction.\n");
        return sb.toString();
    }

    private static String e(String s) {
        return s == null ? "" : s.replace('|', '/').replace('\n', ' ');
    }
}
