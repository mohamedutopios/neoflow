package com.neosoft.neoflow.testsia.generateur;

import java.util.List;

import com.neosoft.neoflow.testsia.modele.DemandeModele;

/**
 * Prompts du générateur. Le message système contient tout ce qui est stable pendant la boucle
 * (consignes, spécification, code de la classe) : il est mis en cache. Le message utilisateur ne porte
 * que ce qui change d'un tour à l'autre (retours du vérificateur, mutants survivants).
 */
public final class PromptsGenerateur {

    public static final String TACHE = "generation-tests";

    public DemandeModele demande(CibleGeneration cible, int tour, List<VerdictTest> rejetes,
            List<VerdictTest> acceptes, List<VerdictTest> aArbitrer, List<String> mutantsSurvivants) {
        return new DemandeModele(TACHE, systeme(cible), utilisateur(tour, rejetes, acceptes, aArbitrer, mutantsSurvivants));
    }

    String systeme(CibleGeneration cible) {
        return """
                Vous écrivez des tests unitaires JUnit 5 pour une application Java 21 (Spring Boot 3.5, mais sans contexte Spring).
                Règles impératives :
                1. L'oracle (valeur attendue) vient de la SPÉCIFICATION ci-dessous, en valeur littérale. Jamais d'appel au code
                   testé ni au code legacy qu'il enveloppe pour calculer la valeur attendue.
                2. Une classe par cas de test, une seule méthode @Test, package %s, nom de classe se terminant par Test.
                3. AssertJ (assertThat) pour les assertions ; Mockito uniquement pour les dépendances de la classe testée,
                   jamais pour la classe testée elle-même. Horloge fixe (Clock.fixed) si le temps intervient.
                4. Aucune exception avalée, aucune assertion constante, pas d'assertion limitée à isNotNull.
                5. Si la spécification ne dit pas ce qui est attendu, n'écrivez pas de test : posez la question dans « questions ».
                6. Le champ « oracle » cite l'exigence (identifiant et phrase) qui fixe la valeur attendue.

                === SPÉCIFICATION ===
                %s

                === CLASSE TESTÉE : %s ===
                %s
                """.formatted(cible.paquet(), cible.specification(), cible.classeCible(), cible.codeSource());
    }

    String utilisateur(int tour, List<VerdictTest> rejetes, List<VerdictTest> acceptes,
            List<VerdictTest> aArbitrer, List<String> mutantsSurvivants) {
        StringBuilder sb = new StringBuilder();
        if (tour == 1) {
            sb.append("Proposez des tests qui couvrent chaque exigence de la spécification, cas limites compris.\n");
            return sb.toString();
        }
        sb.append("Tour ").append(tour).append(". Retours du vérificateur automatique sur vos propositions précédentes.\n");
        if (!rejetes.isEmpty()) {
            sb.append("\nTests REJETÉS : corrigez-les (même exigence, nouveau nom de classe) ou remplacez-les.\n");
            for (VerdictTest v : rejetes) {
                sb.append("- ").append(v.test().nomClasse()).append(" [").append(v.statut()).append("] : ")
                        .append(String.join(" ; ", v.motifs())).append('\n');
            }
        }
        if (!acceptes.isEmpty()) {
            sb.append("\nTests déjà ACCEPTÉS (ne pas les reproposer) : ")
                    .append(String.join(", ", acceptes.stream().map(v -> v.test().nomClasse()).toList())).append('\n');
        }
        if (!aArbitrer.isEmpty()) {
            sb.append("\nTests en attente d'arbitrage humain (ne pas en proposer de variante) : ")
                    .append(String.join(", ", aArbitrer.stream().map(v -> v.test().nomClasse()).toList())).append('\n');
        }
        if (!mutantsSurvivants.isEmpty()) {
            sb.append("\nMutants SURVIVANTS de PIT sur la classe testée : proposez des tests qui les tueraient,\n")
                    .append("en citant l'exigence qui fixe le comportement attendu (sinon, une question).\n");
            mutantsSurvivants.forEach(m -> sb.append("- ").append(m).append('\n'));
        }
        return sb.toString();
    }
}
