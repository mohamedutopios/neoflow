package com.neosoft.neoflow.legacyia.analyse;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.CallableDeclaration;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.Parameter;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.expr.AnnotationExpr;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.NameExpr;
import com.github.javaparser.ast.expr.NormalAnnotationExpr;
import com.github.javaparser.ast.expr.SingleMemberAnnotationExpr;
import com.github.javaparser.ast.expr.StringLiteralExpr;
import com.github.javaparser.ast.expr.ThisExpr;
import com.neosoft.neoflow.legacyia.analyse.Faits.Appel;
import com.neosoft.neoflow.legacyia.analyse.Faits.Champ;
import com.neosoft.neoflow.legacyia.analyse.Faits.Constat;
import com.neosoft.neoflow.legacyia.analyse.Faits.Dependance;
import com.neosoft.neoflow.legacyia.analyse.Faits.FichierSource;
import com.neosoft.neoflow.legacyia.analyse.Faits.Methode;
import com.neosoft.neoflow.legacyia.analyse.Faits.PointEntree;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * Analyse déterministe d'un module legacy et de ses appelants, sans modèle de langage.
 *
 * <p>Résolution des appels <b>par nom</b>, volontairement simple et explicable : la cible d'un appel
 * {@code x.m()} est la classe {@code X} si {@code x} est un nom de classe connu (appel statique), ou le
 * type déclaré du champ, du paramètre ou de la variable {@code x} ; un appel sans portée vise la classe
 * courante. Limites assumées : polymorphisme, lambdas, réflexion et beans injectés par interface ne sont
 * pas résolus. Le graphe est donc un minorant : un appelant absent n'est pas une preuve d'absence.
 */
public final class AnalyseurLegacy {

    private static final Set<String> ANNOTATIONS_HTTP = Set.of(
            "GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping", "RequestMapping");

    private final Path racineSources;
    private final String paquetCible;
    private final CodeSource code = new CodeSource();

    /**
     * @param racineSources racine des sources Java (ex. {@code backend/src/main/java})
     * @param paquetCible   paquet du module legacy (ex. {@code com.neosoft.neoflow.legacy})
     */
    public AnalyseurLegacy(Path racineSources, String paquetCible) {
        this.racineSources = racineSources;
        this.paquetCible = paquetCible;
    }

    /** Code des fichiers retenus, disponible après {@link #analyser()}. */
    public CodeSource code() {
        return code;
    }

    public Faits analyser() {
        Map<String, Unite> unites = lire();
        Map<String, ClasseIndexee> classes = indexer(unites);

        // 1. Toutes les méthodes et tous les appels résolus
        Map<String, Methode> methodes = new LinkedHashMap<>();
        Map<String, CallableDeclaration<?>> declarations = new HashMap<>();
        List<Appel> appels = new ArrayList<>();
        for (ClasseIndexee classe : classes.values()) {
            for (CallableDeclaration<?> declaration : classe.declaration().findAll(CallableDeclaration.class)) {
                if (declaration.findAncestor(TypeDeclaration.class).orElse(null) != classe.declaration()) {
                    continue;   // méthode d'une classe interne : indexée avec elle
                }
                Methode methode = methode(classe, declaration);
                methodes.put(methode.id(), methode);
                declarations.put(methode.id(), declaration);
            }
        }
        for (Map.Entry<String, CallableDeclaration<?>> entree : declarations.entrySet()) {
            Methode appelant = methodes.get(entree.getKey());
            ClasseIndexee classe = classes.get(appelant.classe());
            for (MethodCallExpr appel : entree.getValue().findAll(MethodCallExpr.class)) {
                resoudre(appel, classe, entree.getValue(), classes).ifPresent(cible -> {
                    for (Methode appele : methodes.values()) {
                        if (appele.classe().equals(cible) && appele.nom().equals(appel.getNameAsString())
                                && nbParametres(declarations.get(appele.id())) == appel.getArguments().size()) {
                            appels.add(new Appel(appelant.id(), appele.id(), appelant.fichier(),
                                    appel.getBegin().map(p -> p.line).orElse(0)));
                        }
                    }
                });
            }
        }

        // 2. Sous-graphe : méthodes cibles, appelants transitifs, appelés depuis la cible
        Set<String> cibles = methodes.values().stream().filter(Methode::cible).map(Methode::id)
                .collect(Collectors.toCollection(LinkedHashSet::new));
        Set<String> retenues = new LinkedHashSet<>(cibles);
        retenues.addAll(appelantsTransitifs(cibles, appels));
        appels.stream().filter(a -> cibles.contains(a.appelant())).map(Appel::appele).forEach(retenues::add);

        List<Methode> methodesRetenues = methodes.values().stream().filter(m -> retenues.contains(m.id()))
                .sorted(Comparator.comparing(Methode::fichier).thenComparingInt(Methode::ligneDebut)).toList();
        List<Appel> appelsRetenus = appels.stream()
                .filter(a -> retenues.contains(a.appelant()) && retenues.contains(a.appele()))
                .sorted(Comparator.comparing(Appel::fichier).thenComparingInt(Appel::ligne)).toList();
        Set<String> classesRetenues = methodesRetenues.stream().map(Methode::classe)
                .collect(Collectors.toCollection(LinkedHashSet::new));

        // 3. Fichiers, champs, dépendances, constats, points d'entrée
        List<FichierSource> fichiers = new ArrayList<>();
        List<Champ> champs = new ArrayList<>();
        List<Constat> constats = new ArrayList<>();
        for (String nomClasse : classesRetenues) {
            ClasseIndexee classe = classes.get(nomClasse);
            Unite unite = unites.get(classe.fichier());
            if (fichiers.stream().noneMatch(f -> f.chemin().equals(classe.fichier()))) {
                fichiers.add(new FichierSource(classe.fichier(), unite.lignes().size()));
                code.ajouter(classe.fichier(), unite.contenu());
                if (classe.paquet().equals(paquetCible)) {
                    constats.addAll(new DetecteurConstats(classe.fichier(), unite.ast(), unite.lignes()).detecter());
                }
            }
            champs.addAll(classe.champs());
        }
        Map<String, Integer> compteDependances = new TreeMap<>();
        for (Appel appel : appelsRetenus) {
            String de = classeDe(appel.appelant());
            String vers = classeDe(appel.appele());
            if (!de.equals(vers)) {
                compteDependances.merge(de + "->" + vers, 1, Integer::sum);
            }
        }
        List<Dependance> dependances = compteDependances.entrySet().stream()
                .map(e -> new Dependance(e.getKey().split("->")[0], e.getKey().split("->")[1], e.getValue())).toList();
        List<PointEntree> pointsEntree = new ArrayList<>();
        for (String id : retenues) {
            pointEntree(classes.get(classeDe(id)), declarations.get(id), id).ifPresent(pointsEntree::add);
        }
        return new Faits(paquetCible, fichiers, methodesRetenues, champs, appelsRetenus, dependances, constats,
                pointsEntree);
    }

    /** Appelants directs et indirects d'un ensemble de méthodes (parcours en largeur du graphe inversé). */
    public static Set<String> appelantsTransitifs(Set<String> cibles, List<Appel> appels) {
        Set<String> vus = new LinkedHashSet<>();
        Deque<String> aTraiter = new ArrayDeque<>(cibles);
        while (!aTraiter.isEmpty()) {
            String courant = aTraiter.poll();
            for (Appel appel : appels) {
                if (appel.appele().equals(courant) && !cibles.contains(appel.appelant()) && vus.add(appel.appelant())) {
                    aTraiter.add(appel.appelant());
                }
            }
        }
        return vus;
    }

    // ------------------------------------------------------------------ lecture et index

    private record Unite(String chemin, String contenu, List<String> lignes, CompilationUnit ast) {}

    private record ClasseIndexee(String nom, String paquet, String fichier, ClassOrInterfaceDeclaration declaration,
                                 Map<String, String> typesChamps, List<Champ> champs) {}

    private Map<String, Unite> lire() {
        JavaParser parseur = new JavaParser(new ParserConfiguration()
                .setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_21));
        Map<String, Unite> unites = new TreeMap<>();
        try (Stream<Path> fichiers = Files.walk(racineSources)) {
            for (Path fichier : fichiers.filter(f -> f.toString().endsWith(".java")).sorted().toList()) {
                String contenu = Files.readString(fichier, StandardCharsets.UTF_8);
                ParseResult<CompilationUnit> resultat = parseur.parse(contenu);
                if (resultat.getResult().isEmpty()) {
                    throw new IllegalStateException("Analyse impossible de " + fichier + " : " + resultat.getProblems());
                }
                String chemin = racineSources.relativize(fichier).toString().replace('\\', '/');
                unites.put(chemin, new Unite(chemin, contenu, contenu.lines().toList(), resultat.getResult().get()));
            }
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        return unites;
    }

    private Map<String, ClasseIndexee> indexer(Map<String, Unite> unites) {
        Map<String, ClasseIndexee> classes = new LinkedHashMap<>();
        for (Unite unite : unites.values()) {
            String paquet = unite.ast().getPackageDeclaration().map(p -> p.getNameAsString()).orElse("");
            for (ClassOrInterfaceDeclaration declaration : unite.ast().findAll(ClassOrInterfaceDeclaration.class)) {
                Map<String, String> types = new HashMap<>();
                List<Champ> champs = new ArrayList<>();
                for (FieldDeclaration champ : declaration.getFields()) {
                    for (VariableDeclarator variable : champ.getVariables()) {
                        types.put(variable.getNameAsString(), variable.getType().asString());
                        champs.add(new Champ(declaration.getNameAsString(), variable.getNameAsString(),
                                variable.getType().asString(), unite.chemin(),
                                champ.getBegin().map(p -> p.line).orElse(0), champ.isStatic(), champ.isFinal()));
                    }
                }
                classes.put(declaration.getNameAsString(), new ClasseIndexee(declaration.getNameAsString(), paquet,
                        unite.chemin(), declaration, types, champs));
            }
        }
        return classes;
    }

    private Methode methode(ClasseIndexee classe, CallableDeclaration<?> declaration) {
        String types = declaration.getParameters().stream().map(p -> p.getType().asString())
                .collect(Collectors.joining(","));
        String signature = declaration.getNameAsString() + "(" + declaration.getParameters().stream()
                .map(p -> p.getType().asString() + " " + p.getNameAsString()).collect(Collectors.joining(", ")) + ")";
        return new Methode(classe.nom() + "." + declaration.getNameAsString() + "(" + types + ")", classe.nom(),
                declaration.getNameAsString(), signature, classe.fichier(),
                declaration.getBegin().map(p -> p.line).orElse(0), declaration.getEnd().map(p -> p.line).orElse(0),
                ComplexiteCyclomatique.calculer(declaration), declaration.isPublic(), declaration.isStatic(),
                classe.paquet().equals(paquetCible));
    }

    private static int nbParametres(CallableDeclaration<?> declaration) {
        return declaration == null ? -1 : declaration.getParameters().size();
    }

    /** Classe visée par un appel, résolue par nom (voir la JavaDoc de la classe). */
    private static Optional<String> resoudre(MethodCallExpr appel, ClasseIndexee courante,
                                             CallableDeclaration<?> methode, Map<String, ClasseIndexee> classes) {
        Optional<Expression> portee = appel.getScope();
        if (portee.isEmpty() || portee.get() instanceof ThisExpr) {
            return Optional.of(courante.nom());
        }
        String nom = null;
        if (portee.get() instanceof NameExpr n) {
            nom = n.getNameAsString();
        } else if (portee.get() instanceof FieldAccessExpr f && f.getScope() instanceof ThisExpr) {
            nom = f.getNameAsString();
        }
        if (nom == null) {
            return Optional.empty();
        }
        if (classes.containsKey(nom)) {
            return Optional.of(nom);                                   // appel statique Classe.methode()
        }
        String type = typeLocal(nom, methode).orElse(courante.typesChamps().get(nom));
        return type != null && classes.containsKey(type) ? Optional.of(type) : Optional.empty();
    }

    private static Optional<String> typeLocal(String nom, CallableDeclaration<?> methode) {
        for (Parameter parametre : methode.getParameters()) {
            if (parametre.getNameAsString().equals(nom)) {
                return Optional.of(parametre.getType().asString());
            }
        }
        return methode.findAll(VariableDeclarator.class).stream().filter(v -> v.getNameAsString().equals(nom))
                .map(v -> v.getType().asString()).findFirst();
    }

    private static Optional<PointEntree> pointEntree(ClasseIndexee classe, CallableDeclaration<?> methode, String id) {
        if (classe == null || methode == null) {
            return Optional.empty();
        }
        Optional<AnnotationExpr> mapping = methode.getAnnotations().stream()
                .filter(a -> ANNOTATIONS_HTTP.contains(a.getNameAsString())).findFirst();
        if (mapping.isEmpty()) {
            return Optional.empty();
        }
        String prefixe = classe.declaration().getAnnotationByName("RequestMapping").map(AnalyseurLegacy::chemin).orElse("");
        String verbe = mapping.get().getNameAsString().replace("Mapping", "").toUpperCase();
        return Optional.of(new PointEntree(verbe.equals("REQUEST") ? "*" : verbe, prefixe + chemin(mapping.get()), id));
    }

    private static String chemin(AnnotationExpr annotation) {
        Expression valeur = null;
        if (annotation instanceof SingleMemberAnnotationExpr simple) {
            valeur = simple.getMemberValue();
        } else if (annotation instanceof NormalAnnotationExpr normale) {
            valeur = normale.getPairs().stream().filter(p -> p.getNameAsString().equals("value")
                    || p.getNameAsString().equals("path")).map(p -> p.getValue()).findFirst().orElse(null);
        }
        if (valeur instanceof StringLiteralExpr texte) {
            return texte.getValue();
        }
        return valeur == null ? "" : valeur.findFirst(StringLiteralExpr.class).map(StringLiteralExpr::getValue).orElse("");
    }

    private static String classeDe(String idMethode) {
        return idMethode.substring(0, idMethode.indexOf('.'));
    }
}
