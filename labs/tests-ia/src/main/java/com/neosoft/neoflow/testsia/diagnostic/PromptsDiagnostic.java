package com.neosoft.neoflow.testsia.diagnostic;

import java.util.List;

import com.neosoft.neoflow.testsia.modele.DemandeModele;

/** Prompts de l'assistant de diagnostic : consignes stables en système, dossier et retours en utilisateur. */
public final class PromptsDiagnostic {

    public static final String TACHE = "diagnostic";

    static final String SYSTEME = """
            Vous assistez un développeur Java/Spring Boot dans le diagnostic d'un incident sur NeoFlow.
            Vous recevez un DOSSIER de faits numérotés (F1, F2…), extraits automatiquement des logs ECS et d'une trace
            OpenTelemetry exportée de Jaeger, et éventuellement un extrait du code source.
            Règles :
            1. Ne raisonnez que sur les faits du dossier et l'extrait de code. Toute hypothèse cite les identifiants des
               faits qui la soutiennent (faitsPour) et de ceux qui la contredisent (faitsContre). N'inventez aucun fait.
            2. Trois hypothèses au plus, classées par vraisemblance (1 à 5). Indiquez ce qui réfuterait chacune.
            3. Pour chaque hypothèse, proposez le plus petit test qui la confirmerait : niveau (unitaire, api ou e2e),
               classe, méthode, assertion exacte avec la valeur attendue. Ce test doit échouer avant correctif.
            4. Ne proposez pas de correctif : le diagnostic précède la correction.
            5. Listez dans « inconnues » ce que les artefacts ne permettent pas de savoir, et comment le lever.
            """;

    public DemandeModele demande(DossierIncident dossier, String extraitCode, List<String> rejetsPrecedents) {
        StringBuilder sb = new StringBuilder("=== DOSSIER ===\n").append(dossier.versTexte());
        if (extraitCode != null) {
            sb.append("\n=== EXTRAIT DE CODE (première frame applicative) ===\n").append(extraitCode).append('\n');
        }
        if (!rejetsPrecedents.isEmpty()) {
            sb.append("\nVos hypothèses précédentes ont été rejetées par le contrôle automatique :\n");
            rejetsPrecedents.forEach(r -> sb.append("- ").append(r).append('\n'));
            sb.append("Reformulez en respectant les règles.\n");
        }
        return new DemandeModele(TACHE, SYSTEME, sb.toString());
    }
}
