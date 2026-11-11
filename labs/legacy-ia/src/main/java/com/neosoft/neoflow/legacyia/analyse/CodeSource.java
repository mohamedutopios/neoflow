package com.neosoft.neoflow.legacyia.analyse;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Texte des fichiers analysés, ligne par ligne. Sert à fournir au modèle un code numéroté et à
 * vérifier ses citations.
 */
public final class CodeSource {

    private final Map<String, List<String>> lignesParFichier = new LinkedHashMap<>();

    public void ajouter(String chemin, String contenu) {
        lignesParFichier.put(chemin, contenu.lines().toList());
    }

    public Map<String, List<String>> fichiers() {
        return lignesParFichier;
    }

    /** Résout un chemin exact, ou un nom de fichier seul s'il est unique. */
    public Optional<String> resoudre(String fichier) {
        if (fichier == null || fichier.isBlank()) {
            return Optional.empty();
        }
        String normalise = fichier.replace('\\', '/').strip();
        if (lignesParFichier.containsKey(normalise)) {
            return Optional.of(normalise);
        }
        List<String> candidats = lignesParFichier.keySet().stream()
                .filter(c -> c.endsWith("/" + normalise) || c.equals(normalise))
                .toList();
        return candidats.size() == 1 ? Optional.of(candidats.get(0)) : Optional.empty();
    }

    public List<String> lignes(String cheminResolu) {
        return lignesParFichier.getOrDefault(cheminResolu, List.of());
    }

    /** Code numéroté (« 56 | if (departement == DSI) { ») pour les fichiers demandés. */
    public String numeroter(List<String> chemins) {
        StringBuilder sb = new StringBuilder();
        for (String chemin : chemins) {
            List<String> lignes = lignes(chemin);
            sb.append("=== ").append(chemin).append(" (").append(lignes.size()).append(" lignes)\n");
            for (int i = 0; i < lignes.size(); i++) {
                sb.append(i + 1).append(" | ").append(lignes.get(i)).append('\n');
            }
        }
        return sb.toString();
    }
}
