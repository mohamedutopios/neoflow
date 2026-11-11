package com.neosoft.neoflow.testsia.generateur;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Modifier;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.expr.BooleanLiteralExpr;
import com.github.javaparser.ast.expr.ClassExpr;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.NameExpr;
import com.github.javaparser.ast.stmt.CatchClause;

/**
 * Détecte, par analyse statique (JavaParser), les tests qui ne peuvent pas échouer pour une vraie raison.
 * Sept règles, issues des formes les plus fréquentes chez un agent (slides J7, schéma 04) :
 * <ol>
 *   <li>aucune assertion ;</li>
 *   <li>assertion constante ({@code assertTrue(true)}, expression comparée à elle-même) ;</li>
 *   <li>exception avalée ({@code catch} vide) ;</li>
 *   <li>classe testée mockée ;</li>
 *   <li>oracle recalculé : la valeur attendue appelle le code testé (ou le legacy qu'il enveloppe) ;</li>
 *   <li>assertions toutes trop faibles ({@code isNotNull}, {@code assertNotNull}) ;</li>
 *   <li>la valeur attendue est celle que renvoie un stub ({@code when(...).thenReturn(x)} puis {@code isEqualTo(x)}).</li>
 * </ol>
 * Une liste vide signifie « rien de tautologique détecté », pas « test utile » : le score de mutation complète.
 */
public final class AnalyseurTautologies {

    private static final Set<String> ATTENTES = Set.of("isEqualTo", "isEqualByComparingTo", "containsExactly",
            "isSameAs", "hasValue", "contains", "isEqualToIgnoringCase");
    private static final Set<String> FAIBLES = Set.of("isNotNull", "assertNotNull", "isInstanceOf", "isNotEmpty");

    /** Noms des méthodes publiques de la classe cible, extraits de son code source. */
    public static Set<String> methodesPubliques(String sourceCible) {
        Set<String> noms = new LinkedHashSet<>();
        StaticJavaParser.parse(sourceCible).findAll(MethodDeclaration.class).stream()
                .filter(m -> m.hasModifier(Modifier.Keyword.PUBLIC))
                .forEach(m -> noms.add(m.getNameAsString()));
        return noms;
    }

    /**
     * @param source          code de la classe de test proposée
     * @param classeCible     nom simple de la classe testée
     * @param methodesCible   méthodes publiques de la classe testée (voir {@link #methodesPubliques})
     * @return motifs de rejet, en français, vides si aucune tautologie n'est détectée
     */
    public List<String> analyser(String source, String classeCible, Set<String> methodesCible) {
        // TODO J07-2 (tests : AnalyseurTautologiesTest) — parser la source (StaticJavaParser.parse) et renvoyer un motif
        // par règle enfreinte, pour chaque méthode @Test (ou @ParameterizedTest) :
        //  1. aucune assertion (appel dont le nom commence par assert, ou verify, ou fail) ;
        //  2. assertion constante : assertTrue(true), assertThat(true), assertEquals(x, x), assertThat(x).isEqualTo(x) ;
        //  3. exception avalée : CatchClause au corps vide ;
        //  4. classe testée mockée : mock(Cible.class) / spy(...), champ @Mock/@Spy/@MockitoBean/@MockBean de type Cible ;
        //  5. oracle recalculé : la valeur attendue (voir valeursAttendues) appelle une méthode de methodesCible
        //     ou une classe *Legacy ;
        //  6. toutes les assertions sont faibles (voir estFaible) ;
//  7. (extension TP 1) la valeur attendue est un nom passé à thenReturn(...) / doReturn(...) : le test vérifie Mockito.
        // Les motifs sont renvoyés au modèle : écrivez-les pour qu'il comprenne quoi corriger.
        throw new UnsupportedOperationException("TODO J07-2 : AnalyseurTautologies.analyser");
    }

    /**
     * Valeurs attendues : arguments de isEqualTo(...) & co, premier argument d'assertEquals(...).
     * Une variable locale est remplacée par son initialisation ({@code int attendu = legacy(...)}).
     */
    private static List<Expression> valeursAttendues(MethodDeclaration methode) {
        List<Expression> attendues = new ArrayList<>();
        for (MethodCallExpr appel : methode.findAll(MethodCallExpr.class)) {
            if (ATTENTES.contains(appel.getNameAsString())) {
                attendues.addAll(appel.getArguments());
            }
            if (appel.getNameAsString().equals("assertEquals") && !appel.getArguments().isEmpty()) {
                attendues.add(appel.getArgument(0));
            }
        }
        List<Expression> resolues = new ArrayList<>(attendues);
        for (Expression e : attendues) {
            if (e instanceof NameExpr nom) {
                methode.findAll(VariableDeclarator.class).stream()
                        .filter(v -> v.getNameAsString().equals(nom.getNameAsString()))
                        .forEach(v -> v.getInitializer().ifPresent(resolues::add));
            }
        }
        return resolues;
    }

    private static Expression racineAssertThat(Expression e) {
        Expression courant = e;
        while (courant instanceof MethodCallExpr m && !m.getNameAsString().equals("assertThat") && m.getScope().isPresent()) {
            courant = m.getScope().get();
        }
        return courant instanceof MethodCallExpr m && m.getNameAsString().equals("assertThat") ? m : null;
    }

    /** assertNotNull(x), ou une chaîne assertThat(x).isNotNull() dont toutes les vérifications sont faibles. */
    private static boolean estFaible(MethodCallExpr assertion, MethodDeclaration methode) {
        if (FAIBLES.contains(assertion.getNameAsString())) {
            return true;
        }
        if (!assertion.getNameAsString().equals("assertThat")) {
            return false;
        }
        List<String> verifications = new ArrayList<>();
        var parent = assertion.getParentNode();
        while (parent.isPresent() && parent.get() instanceof MethodCallExpr m) {
            verifications.add(m.getNameAsString());
            parent = m.getParentNode();
        }
        return !verifications.isEmpty() && verifications.stream().allMatch(FAIBLES::contains);
    }
}
