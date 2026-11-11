package com.neosoft.neoflow.testsia.generateur;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import com.neosoft.neoflow.testsia.commun.Journal;
import com.neosoft.neoflow.testsia.modele.Consommation;
import com.neosoft.neoflow.testsia.modele.DemandeModele;
import com.neosoft.neoflow.testsia.modele.ModeleLangage;
import com.neosoft.neoflow.testsia.modele.ReponseModele;

/**
 * Pattern Generator–Verifier borné : le modèle propose, le vérificateur déterministe juge,
 * les rejets (avec leur motif) et les mutants survivants repartent au modèle, au plus {@code toursMax} fois.
 * <p>
 * Arrêt : plus aucun rejet et (mutation désactivée ou score atteint), ou tours épuisés.
 */
public final class GenerateurVerifie {

    private final ModeleLangage modele;
    private final Verificateur verificateur;
    private final MesureMutation mutation;
    private final PromptsGenerateur prompts = new PromptsGenerateur();
    private final Journal journal;

    /** @param mutation {@code null} pour désactiver PIT (plus rapide, moins de preuves) */
    public GenerateurVerifie(ModeleLangage modele, Verificateur verificateur, MesureMutation mutation, Journal journal) {
        this.modele = modele;
        this.verificateur = verificateur;
        this.mutation = mutation;
        this.journal = journal;
    }

    public RapportGeneration generer(CibleGeneration cible, ContexteProjet projet, int toursMax, double seuilMutation) {
        // TODO J07-3 (tests : GenerateurVerifieTest) — boucle Generator–Verifier BORNÉE, au plus toursMax tours :
        //  1. demande = prompts.demande(cible, tour, rejetesDuTour, acceptés, à arbitrer, mutantsSurvivants) ;
        //  2. reponse = modele.demander(demande, PropositionTests.class) ; cumuler la consommation ; journaliser ("llm") ;
        //     collecter les questions du modèle ;
        //  3. verdicts = verificateur.verifier(reponse.contenu(), cible, projet, tour) ; rejetesDuTour = verdicts rejetés ;
        //  4. si mutation != null et au moins un test accepté : mutation.mesurer(classe cible, noms qualifiés des acceptés,
        //     verificateur.classesTests(projet), projet) ; survivants = mutants survivants ;
        //  5. arrêt si aucun rejet ce tour ET (mutation désactivée OU score >= seuilMutation).
        // Règle clé : un test ROUGE_A_ARBITRER n'est jamais renvoyé avec son échec (le modèle alignerait l'oracle sur le code).
        // Retour : new RapportGeneration(cible.classeCible(), modele.nom(), tour, tous les verdicts, mutation, questions, consommation).
        throw new UnsupportedOperationException("TODO J07-3 : GenerateurVerifie.generer");
    }

    private static List<VerdictTest> filtrer(List<VerdictTest> verdicts, Statut statut) {
        return verdicts.stream().filter(v -> v.statut() == statut).toList();
    }

    private static String resume(List<VerdictTest> verdicts) {
        return String.join(", ", verdicts.stream().map(v -> v.test().nomClasse() + "=" + v.statut()).toList());
    }
}
