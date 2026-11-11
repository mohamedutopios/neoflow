package com.neosoft.neoflow.legacyia.analyse;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.CallableDeclaration;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.Parameter;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.expr.BinaryExpr;
import com.github.javaparser.ast.expr.DoubleLiteralExpr;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.IntegerLiteralExpr;
import com.github.javaparser.ast.expr.LiteralStringValueExpr;
import com.github.javaparser.ast.expr.LongLiteralExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.NameExpr;
import com.github.javaparser.ast.expr.NullLiteralExpr;
import com.github.javaparser.ast.expr.ObjectCreationExpr;
import com.github.javaparser.ast.expr.StringLiteralExpr;
import com.github.javaparser.ast.expr.UnaryExpr;
import com.neosoft.neoflow.legacyia.analyse.Faits.Constat;
import com.neosoft.neoflow.legacyia.analyse.Faits.TypeConstat;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * Détecteurs déterministes de dette et de risques sur un fichier du module cible.
 * Chaque constat porte la ligne et l'extrait exact : ce sont des faits, pas des opinions.
 */
public final class DetecteurConstats {

    /** Valeurs tolérées (convention Checkstyle MagicNumber). */
    private static final Set<String> NOMBRES_TOLERES = Set.of("-1", "0", "1", "2");

    /** Appels qui lisent l'horloge ou le fuseau du système sans passer par une {@code Clock} injectée. */
    private static final Map<String, Set<String>> APPELS_HORLOGE = Map.of(
            "Calendar", Set.of("getInstance"),
            "System", Set.of("currentTimeMillis", "nanoTime"),
            "LocalDate", Set.of("now"), "LocalDateTime", Set.of("now"), "LocalTime", Set.of("now"),
            "ZonedDateTime", Set.of("now"), "OffsetDateTime", Set.of("now"), "Instant", Set.of("now"),
            "Clock", Set.of("systemDefaultZone", "systemUTC"));

    private final String fichier;
    private final CompilationUnit unite;
    private final List<String> lignes;

    public DetecteurConstats(String fichier, CompilationUnit unite, List<String> lignes) {
        this.fichier = fichier;
        this.unite = unite;
        this.lignes = lignes;
    }

    /** Tous les constats du fichier, triés par ligne. */
    public List<Constat> detecter() {
        List<Constat> constats = new ArrayList<>();
        constats.addAll(nombresMagiques());
        constats.addAll(comparaisonsReferenceString());
        constats.addAll(horlogeCachee());
        constats.addAll(etatStatiqueMutable());
        constats.addAll(localeImplicite());
        constats.addAll(divisionsEntieres());
        constats.sort(Comparator.comparingInt(Constat::ligne).thenComparing(c -> c.type().name()));
        return constats;
    }

    /** Littéraux numériques hors {-1, 0, 1, 2} et hors initialisation de champ. */
    List<Constat> nombresMagiques() {
        List<Constat> constats = new ArrayList<>();
        List<LiteralStringValueExpr> litteraux = new ArrayList<>();
        litteraux.addAll(unite.findAll(IntegerLiteralExpr.class));
        litteraux.addAll(unite.findAll(LongLiteralExpr.class));
        litteraux.addAll(unite.findAll(DoubleLiteralExpr.class));
        for (LiteralStringValueExpr litteral : litteraux) {
            if (litteral.findAncestor(FieldDeclaration.class).isPresent()) {
                continue;   // définition d'une constante (même mutable) : signalée ailleurs si besoin
            }
            String valeur = litteral.getValue();
            boolean negatif = litteral.getParentNode().filter(p -> p instanceof UnaryExpr u
                    && u.getOperator() == UnaryExpr.Operator.MINUS).isPresent();
            if (NOMBRES_TOLERES.contains((negatif ? "-" : "") + valeur)) {
                continue;
            }
            constats.add(constat(TypeConstat.NOMBRE_MAGIQUE, litteral, (negatif ? "-" : "") + valeur,
                    "nombre magique " + (negatif ? "-" : "") + valeur + " : le nommer sans changer l'opérateur qui l'utilise"));
        }
        return constats;
    }

    /**
     * {@code ==} ou {@code !=} entre deux expressions dont l'une est de type {@code String}
     * (littéral, champ, paramètre ou variable locale déclarés {@code String}). Les tests
     * {@code == null} sont légitimes et ignorés.
     */
    List<Constat> comparaisonsReferenceString() {
        List<Constat> constats = new ArrayList<>();
        // TODO TP1-2 : pour chaque BinaryExpr d'opérateur EQUALS ou NOT_EQUALS de l'unité :
        //   - ignorer les comparaisons avec null (NullLiteralExpr) : elles sont légitimes ;
        //   - si estString(gauche, comparaison) ou estString(droite, comparaison), ajouter
        //     constat(TypeConstat.COMPARAISON_REFERENCE_STRING, comparaison, comparaison.toString(), "...").
        // Attendu : un seul constat, RegleValidationLegacy.java:56 « departement == DSI ».
        return constats;
    }

    /** Lecture de l'horloge ou du fuseau système : {@code Calendar.getInstance()}, {@code now()}, {@code new Date()}. */
    List<Constat> horlogeCachee() {
        List<Constat> constats = new ArrayList<>();
        // TODO TP1-3 : repérer les lectures de l'horloge système.
        //   - MethodCallExpr dont la portée est un NameExpr présent dans APPELS_HORLOGE et dont le nom figure
        //     dans l'ensemble associé (now() seulement sans argument ; Clock.systemDefaultZone() toujours) ;
        //   - ObjectCreationExpr « new Date() » ou « new GregorianCalendar() » sans argument.
        // Attendu : RegleValidationLegacy.java:86 « Calendar.getInstance() ».
        return constats;
    }

    /** Champs {@code static} non {@code final} : état global modifiable par tout appelant. */
    List<Constat> etatStatiqueMutable() {
        List<Constat> constats = new ArrayList<>();
        for (FieldDeclaration champ : unite.findAll(FieldDeclaration.class)) {
            boolean dansInterface = champ.findAncestor(ClassOrInterfaceDeclaration.class)
                    .map(ClassOrInterfaceDeclaration::isInterface).orElse(false);
            if (champ.isStatic() && !champ.isFinal() && !dansInterface) {
                for (VariableDeclarator variable : champ.getVariables()) {
                    constats.add(constat(TypeConstat.ETAT_STATIQUE_MUTABLE, champ, variable.toString(),
                            "champ static non final : état global partagé, modifiable par n'importe quel code"));
                }
            }
        }
        return constats;
    }

    /** {@code toUpperCase()} / {@code toLowerCase()} sans {@code Locale} : dépend de la Locale de la JVM. */
    List<Constat> localeImplicite() {
        List<Constat> constats = new ArrayList<>();
        for (MethodCallExpr appel : unite.findAll(MethodCallExpr.class)) {
            String nom = appel.getNameAsString();
            if ((nom.equals("toUpperCase") || nom.equals("toLowerCase")) && appel.getArguments().isEmpty()) {
                constats.add(constat(TypeConstat.LOCALE_IMPLICITE, appel, appel.toString(),
                        "casse dépendante de la Locale de la JVM (\"dsi\" en turc) : préciser Locale.ROOT"));
            }
        }
        return constats;
    }

    /** {@code Math.round(x) / n} : {@code long} divisé par un entier, la partie décimale est perdue. */
    List<Constat> divisionsEntieres() {
        List<Constat> constats = new ArrayList<>();
        for (BinaryExpr division : unite.findAll(BinaryExpr.class)) {
            if (division.getOperator() == BinaryExpr.Operator.DIVIDE
                    && division.getLeft() instanceof MethodCallExpr appel
                    && appel.getNameAsString().equals("round")
                    && appel.getScope().map(s -> s.toString().equals("Math")).orElse(false)
                    && (division.getRight() instanceof IntegerLiteralExpr || division.getRight() instanceof LongLiteralExpr)) {
                constats.add(constat(TypeConstat.DIVISION_ENTIERE, division, division.toString(),
                        "Math.round renvoie un long : la division par un entier tronque (25,5 devient 25)"));
            }
        }
        return constats;
    }

    // ------------------------------------------------------------------ outils

    private boolean estString(Expression expression, Node contexte) {
        if (expression instanceof StringLiteralExpr) {
            return true;
        }
        if (!(expression instanceof NameExpr nom)) {
            return false;
        }
        String identifiant = nom.getNameAsString();
        // paramètres et variables locales de la méthode englobante
        Optional<CallableDeclaration> methode = contexte.findAncestor(CallableDeclaration.class);
        if (methode.isPresent()) {
            for (Object p : methode.get().getParameters()) {
                Parameter parametre = (Parameter) p;
                if (parametre.getNameAsString().equals(identifiant)) {
                    return parametre.getType().asString().equals("String");
                }
            }
            for (VariableDeclarator locale : methode.get().findAll(VariableDeclarator.class)) {
                if (locale.getNameAsString().equals(identifiant)) {
                    return locale.getType().asString().equals("String");
                }
            }
        }
        // champs de la classe
        return contexte.findAncestor(ClassOrInterfaceDeclaration.class).stream()
                .flatMap(c -> c.getFields().stream())
                .flatMap(f -> f.getVariables().stream())
                .filter(v -> v.getNameAsString().equals(identifiant))
                .anyMatch(v -> v.getType().asString().equals("String"));
    }

    private Constat constat(TypeConstat type, Node noeud, String extraitNoeud, String detail) {
        int ligne = noeud.getBegin().map(p -> p.line).orElse(0);
        String methode = noeud.findAncestor(CallableDeclaration.class)
                .map(m -> ((CallableDeclaration<?>) m).getNameAsString()).orElse(null);
        String texteLigne = ligne >= 1 && ligne <= lignes.size() ? lignes.get(ligne - 1).strip() : extraitNoeud;
        // L'extrait est la ligne réelle quand elle contient le nœud (premier niveau de vérification)
        String extrait = texteLigne.contains(premiereLigne(extraitNoeud)) ? premiereLigne(extraitNoeud) : texteLigne;
        return new Constat(type, fichier, ligne, methode, extrait, detail);
    }

    private static String premiereLigne(String texte) {
        int fin = texte.indexOf('\n');
        return (fin < 0 ? texte : texte.substring(0, fin)).strip();
    }
}
