package com.neosoft.neoflow.legacyia.ia;

import com.neosoft.neoflow.legacyia.analyse.Faits;

import java.util.List;

/**
 * Partie déterministe d'une analyse d'impact : calculée par le graphe d'appels, avant tout appel au modèle.
 *
 * @param cible                ligne visée, {@code fichier:ligne}
 * @param changement           changement proposé, en clair
 * @param methodeModifiee      méthode qui contient la ligne
 * @param appelants            appelants transitifs de cette méthode
 * @param chaine               appels qui mènent à la méthode modifiée (fichier:ligne de chaque appel)
 * @param pointsEntree         endpoints HTTP atteints
 * @param methodesPointsEntree méthodes de contrôleur correspondantes (pour les citer)
 * @param constatsSurLaLigne   constats déjà relevés sur la ligne visée
 */
public record ImpactDeterministe(String cible, String changement, String methodeModifiee, List<String> appelants,
                                 List<Faits.Appel> chaine, List<Faits.PointEntree> pointsEntree,
                                 List<Faits.Methode> methodesPointsEntree, List<Faits.Constat> constatsSurLaLigne) {}
