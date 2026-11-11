package com.neosoft.neoflow.legacyia.traduction;

import com.neosoft.neoflow.legacyia.ia.ModeleLangage;
import com.neosoft.neoflow.legacyia.ia.Reponses.TraductionTs;
import com.neosoft.neoflow.legacyia.ia.Requete;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.List;
import java.util.Optional;

/**
 * Boucle « le modèle traduit, les tests de parité jugent » :
 * <ol>
 *   <li>le modèle traduit {@code utils-legacy.js} (sortie structurée) ;</li>
 *   <li>la candidate est écrite à la place de {@code src/utils/utils.ts} (l'original est sauvegardé) ;</li>
 *   <li>les tests de parité Vitest sont lancés ;</li>
 *   <li>la candidate n'est conservée que si la parité est verte <b>et</b> que l'humain l'a demandé
 *       ({@code conserver}) ; sinon l'original est restauré. Une copie est toujours laissée dans le dossier de sortie.</li>
 * </ol>
 */
public final class TraducteurJsTs {

    static final String SYSTEME = """
            Vous traduisez un fichier JavaScript ES5 de l'application NeoFlow en TypeScript strict, à comportement \
            STRICTEMENT identique : mêmes sorties pour toutes les entrées, y compris les bizarreries (arrondi \
            binaire, dates « AAAA-MM-JJ » lues en UTC, jours fériés comptés, NaN, valeurs vides).
            Interdits : Intl.NumberFormat, toLocaleString, toLocaleDateString, toute bibliothèque, toute correction \
            de bug, tout changement de format (séparateur de milliers : espace U+0020).
            Attendus : types au moins aussi larges que les usages réels ; TSDoc avec « @remarks Comportement \
            hérité » pour chaque bizarrerie conservée ; export par défaut compatible avec l'objet NeoUtils \
            (formatMontant, formatDate, joursOuvres) ; fichier complet, sans dépendance.
            Les tests de parité seront exécutés sur votre code.""";

    private final ModeleLangage modele;
    private final ExecuteurParite executeur;

    public TraducteurJsTs(ModeleLangage modele, ExecuteurParite executeur) {
        this.modele = modele;
        this.executeur = executeur;
    }

    /** Résultat d'une traduction. */
    public record Resultat(boolean pariteVerte, boolean conservee, Path copieCandidate, List<String> remarques,
                           String sortieTests) {}

    /**
     * @param dossierFrontend dossier {@code frontend/} (contient {@code src/legacy/utils-legacy.js})
     * @param sortie          dossier où laisser la copie de la candidate
     * @param conserver       garder la candidate si la parité est verte (décision humaine explicite)
     * @param contexte        contexte du modèle simulé (ignoré par Claude)
     */
    public Resultat traduire(Path dossierFrontend, Path sortie, boolean conserver, Object contexte) {
        Path legacy = dossierFrontend.resolve("src/legacy/utils-legacy.js");
        Path cible = dossierFrontend.resolve("src/utils/utils.ts");
        try {
            String js = Files.readString(legacy, StandardCharsets.UTF_8);
            TraductionTs traduction = modele.generer(new Requete(Requete.Tache.TRADUIRE, SYSTEME,
                    "Fichier src/legacy/utils-legacy.js :\n```js\n" + js + "\n```", contexte), TraductionTs.class);

            Files.createDirectories(sortie);
            Path copie = sortie.resolve("utils.candidat.ts");
            Files.writeString(copie, traduction.codeTypeScript(), StandardCharsets.UTF_8);

            Files.createDirectories(cible.getParent());
            Optional<Path> sauvegarde = Optional.empty();
            if (Files.exists(cible)) {
                Path s = sortie.resolve("utils.ts.sauvegarde");
                Files.copy(cible, s, StandardCopyOption.REPLACE_EXISTING);
                sauvegarde = Optional.of(s);
            }
            Files.writeString(cible, traduction.codeTypeScript(), StandardCharsets.UTF_8);
            ExecuteurParite.Resultat parite;
            try {
                parite = executeur.executer(dossierFrontend);
            } catch (RuntimeException e) {
                restaurer(cible, sauvegarde);
                throw e;
            }
            boolean garder = parite.vert() && conserver;
            if (!garder) {
                restaurer(cible, sauvegarde);
            }
            return new Resultat(parite.vert(), garder, copie,
                    traduction.remarques() == null ? List.of() : traduction.remarques(), parite.sortie());
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static void restaurer(Path cible, Optional<Path> sauvegarde) throws IOException {
        if (sauvegarde.isPresent()) {
            Files.copy(sauvegarde.get(), cible, StandardCopyOption.REPLACE_EXISTING);
        } else {
            Files.deleteIfExists(cible);
        }
    }
}
