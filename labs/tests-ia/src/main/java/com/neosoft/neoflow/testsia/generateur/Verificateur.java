package com.neosoft.neoflow.testsia.generateur;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.github.javaparser.ParseProblemException;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;

/**
 * Vérifie chaque test proposé, du moins cher au plus cher : structure, tautologies, compilation, exécution.
 * Un test qui compile mais échoue est ROUGE_A_ARBITRER : le vérificateur ne sait pas si le code ou l'oracle
 * a tort, et ce verdict n'est jamais renvoyé au modèle (il « corrigerait » l'oracle pour coller au code).
 */
public final class Verificateur {

    private final AnalyseurTautologies analyseur = new AnalyseurTautologies();
    private final Compilateur compilateur = new Compilateur();
    private final ExecuteurTests executeur;

    public Verificateur(ExecuteurTests executeur) {
        this.executeur = executeur;
    }

    public Path classesTests(ContexteProjet projet) {
        return projet.travail().resolve("classes-tests");
    }

    public List<VerdictTest> verifier(PropositionTests proposition, CibleGeneration cible, ContexteProjet projet, int tour) {
        Set<String> methodesCible = AnalyseurTautologies.methodesPubliques(cible.codeSource());
        List<VerdictTest> verdicts = new ArrayList<>();
        Map<String, TestPropose> compiles = new LinkedHashMap<>();
        List<Path> cp = new ArrayList<>(projet.classpath());
        cp.add(classesTests(projet));
        for (TestPropose test : proposition.tests()) {
            String nomQualifie = cible.paquet().isEmpty() ? test.nomClasse() : cible.paquet() + "." + test.nomClasse();
            List<String> structure = structure(test, cible);
            if (!structure.isEmpty()) {
                verdicts.add(new VerdictTest(test, Statut.REJETE_STRUCTURE, structure, tour));
                continue;
            }
            List<String> tautologies = analyseur.analyser(test.source(), cible.nomSimple(), methodesCible);
            if (!tautologies.isEmpty()) {
                verdicts.add(new VerdictTest(test, Statut.REJETE_TAUTOLOGIE, tautologies, tour));
                continue;
            }
            Compilateur.Resultat c = compilateur.compiler(nomQualifie, test.source(), cp, classesTests(projet));
            if (!c.reussi()) {
                verdicts.add(new VerdictTest(test, Statut.REJETE_COMPILATION,
                        c.erreurs().subList(0, Math.min(5, c.erreurs().size())), tour));
                continue;
            }
            compiles.put(nomQualifie, test);
        }
        if (!compiles.isEmpty()) {
            Map<String, ExecuteurTests.Resultat> resultats =
                    executeur.executer(List.copyOf(compiles.keySet()), classesTests(projet), projet);
            compiles.forEach((nom, test) -> {
                ExecuteurTests.Resultat r = resultats.get(nom);
                if (r.reussi()) {
                    verdicts.add(new VerdictTest(test, Statut.ACCEPTE, List.of(r.nbTests() + " test(s) vert(s)"), tour));
                } else {
                    verdicts.add(new VerdictTest(test, Statut.ROUGE_A_ARBITRER, List.of(r.message()), tour));
                }
            });
        }
        return verdicts;
    }

    private static List<String> structure(TestPropose test, CibleGeneration cible) {
        List<String> motifs = new ArrayList<>();
        if (test.nomClasse() == null || !test.nomClasse().matches("[A-Z][A-Za-z0-9_]*Test")) {
            motifs.add("nom de classe invalide (attendu : [A-Z]…Test) : " + test.nomClasse());
            return motifs;
        }
        try {
            CompilationUnit cu = StaticJavaParser.parse(test.source());
            String paquet = cu.getPackageDeclaration().map(p -> p.getNameAsString()).orElse("");
            if (!paquet.equals(cible.paquet())) {
                motifs.add("package « " + paquet + " » au lieu de « " + cible.paquet() + " »");
            }
            if (cu.getClassByName(test.nomClasse()).isEmpty()) {
                motifs.add("la classe " + test.nomClasse() + " n'est pas déclarée dans la source");
            }
            boolean aUnTest = cu.findAll(MethodDeclaration.class).stream()
                    .anyMatch(m -> m.getAnnotationByName("Test").isPresent() || m.getAnnotationByName("ParameterizedTest").isPresent());
            if (!aUnTest) {
                motifs.add("aucune méthode @Test");
            }
        } catch (ParseProblemException e) {
            motifs.add("source Java illisible : " + e.getProblems().get(0).getMessage());
        }
        return motifs;
    }
}
