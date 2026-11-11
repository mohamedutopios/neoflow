package com.neosoft.neoflow.legacyia;

import com.neosoft.neoflow.legacyia.ia.ContexteTraduction;
import com.neosoft.neoflow.legacyia.ia.ModeleSimule;
import com.neosoft.neoflow.legacyia.analyse.CodeSource;
import com.neosoft.neoflow.legacyia.traduction.ExecuteurParite;
import com.neosoft.neoflow.legacyia.traduction.TraducteurJsTs;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;

/** La parité est simulée (pas de Node dans les tests unitaires) : « rouge » si la candidate instancie Intl.NumberFormat. */
@DisplayName("Traduction JS → TS : la candidate n'est gardée que si la parité est verte et demandée")
class TraducteurJsTsTest {

    private final ExecuteurParite pariteSimulee = dossier -> {
        try {
            String candidate = Files.readString(dossier.resolve("src/utils/utils.ts"));
            boolean vert = !candidate.contains("new Intl.NumberFormat");
            return new ExecuteurParite.Resultat(vert, vert ? 0 : 1, vert ? "5 passed" : "2 failed");
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    };

    private Path frontend(Path dossier, String utilsExistant) throws IOException {
        Path fe = dossier.resolve("frontend");
        Files.createDirectories(fe.resolve("src/legacy"));
        Files.writeString(fe.resolve("src/legacy/utils-legacy.js"), "var NeoUtils = {};");
        if (utilsExistant != null) {
            Files.createDirectories(fe.resolve("src/utils"));
            Files.writeString(fe.resolve("src/utils/utils.ts"), utilsExistant);
        }
        return fe;
    }

    private TraducteurJsTs traducteur() {
        return new TraducteurJsTs(new ModeleSimule(new CodeSource(), null), pariteSimulee);
    }

    @Test
    void traductionNaiveRejeteeEtOriginalRestaure(@TempDir Path dossier) throws IOException {
        Path fe = frontend(dossier, "// original");
        var resultat = traducteur().traduire(fe, dossier.resolve("sortie"), true, new ContexteTraduction("naive", null));

        assertThat(resultat.pariteVerte()).isFalse();
        assertThat(resultat.conservee()).isFalse();
        assertThat(Files.readString(fe.resolve("src/utils/utils.ts"))).isEqualTo("// original");
        assertThat(Files.readString(resultat.copieCandidate())).contains("Intl.NumberFormat");
    }

    @Test
    void traductionFideleGardeeSeulementSiDemande(@TempDir Path dossier) throws IOException {
        Path fe = frontend(dossier, null);
        Path candidate = Files.writeString(dossier.resolve("revue.ts"),
                "/** @remarks Comportement hérité : séparateur U+0020. */\nexport default {};\n");
        ContexteTraduction fidele = new ContexteTraduction("fichier", candidate);   // = --reponse-simulee revue.ts
        var sansAccord = traducteur().traduire(fe, dossier.resolve("s1"), false, fidele);
        assertThat(sansAccord.pariteVerte()).isTrue();
        assertThat(sansAccord.conservee()).isFalse();
        assertThat(fe.resolve("src/utils/utils.ts")).doesNotExist();

        var avecAccord = traducteur().traduire(fe, dossier.resolve("s2"), true, fidele);
        assertThat(avecAccord.conservee()).isTrue();
        assertThat(Files.readString(fe.resolve("src/utils/utils.ts"))).contains("@remarks Comportement hérité");
    }
}
