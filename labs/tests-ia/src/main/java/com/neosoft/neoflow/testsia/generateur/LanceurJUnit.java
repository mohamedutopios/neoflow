package com.neosoft.neoflow.testsia.generateur;

import static org.junit.platform.engine.discovery.DiscoverySelectors.selectClass;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.junit.platform.engine.TestExecutionResult;
import org.junit.platform.launcher.Launcher;
import org.junit.platform.launcher.LauncherDiscoveryRequest;
import org.junit.platform.launcher.TestExecutionListener;
import org.junit.platform.launcher.TestIdentifier;
import org.junit.platform.launcher.core.LauncherDiscoveryRequestBuilder;
import org.junit.platform.launcher.core.LauncherFactory;
import org.junit.platform.engine.support.descriptor.MethodSource;

/**
 * Point d'entrée de la JVM fille qui exécute les tests proposés (aucune dépendance hors JUnit Platform).
 * Sortie : une ligne {@code RESULTAT|classe|REUSSI|ECHEC|nbTests|message} par classe.
 */
public final class LanceurJUnit {

    private LanceurJUnit() {
    }

    public static void main(String[] classes) {
        Map<String, int[]> compteurs = new ConcurrentHashMap<>();
        Map<String, List<String>> messages = new ConcurrentHashMap<>();
        TestExecutionListener ecouteur = new TestExecutionListener() {
            @Override
            public void executionFinished(TestIdentifier id, TestExecutionResult resultat) {
                if (!id.isTest() || id.getSource().isEmpty() || !(id.getSource().get() instanceof MethodSource m)) {
                    return;
                }
                int[] c = compteurs.computeIfAbsent(m.getClassName(), k -> new int[2]);
                c[0]++;
                if (resultat.getStatus() != TestExecutionResult.Status.SUCCESSFUL) {
                    c[1]++;
                    String message = resultat.getThrowable().map(t -> t.getClass().getName() + ": " + t.getMessage())
                            .orElse(resultat.getStatus().toString());
                    messages.computeIfAbsent(m.getClassName(), k -> new ArrayList<>())
                            .add(m.getMethodName() + " -> " + message.replace('\n', ' ').replace('|', '/'));
                }
            }
        };
        LauncherDiscoveryRequestBuilder requete = LauncherDiscoveryRequestBuilder.request();
        for (String classe : classes) {
            requete.selectors(selectClass(classe));
        }
        LauncherDiscoveryRequest demande = requete.build();
        Launcher launcher = LauncherFactory.create();
        launcher.execute(demande, ecouteur);
        for (String classe : classes) {
            int[] c = compteurs.getOrDefault(classe, new int[2]);
            String statut = c[0] > 0 && c[1] == 0 ? "REUSSI" : "ECHEC";
            String message = c[0] == 0 ? "aucun test exécuté" : String.join(" ; ", messages.getOrDefault(classe, List.of()));
            System.out.println("RESULTAT|" + classe + "|" + statut + "|" + c[0] + "|" + message);
        }
    }
}
