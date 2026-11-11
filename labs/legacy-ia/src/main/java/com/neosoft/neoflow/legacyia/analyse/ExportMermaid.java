package com.neosoft.neoflow.legacyia.analyse;

import com.neosoft.neoflow.legacyia.analyse.Faits.Appel;
import com.neosoft.neoflow.legacyia.analyse.Faits.Methode;
import com.neosoft.neoflow.legacyia.analyse.Faits.PointEntree;

import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/** Diagrammes Mermaid calculés à partir des faits (aucune intervention du modèle). */
public final class ExportMermaid {

    private ExportMermaid() {
    }

    /** Graphe des appels : endpoints, appelants, méthodes du module cible (encadrées en rouge). */
    public static String grapheAppels(Faits faits) {
        StringBuilder sb = new StringBuilder("flowchart LR\n");
        Map<String, String> ids = new LinkedHashMap<>();
        for (Methode m : faits.methodes()) {
            ids.put(m.id(), "m" + ids.size());
        }
        long nbConstats;
        sb.append("  subgraph cible[\"").append(faits.paquetCible()).append("\"]\n");
        for (Methode m : faits.methodes()) {
            if (m.cible()) {
                nbConstats = faits.constats().stream().filter(c -> m.nom().equals(c.methode())
                        && c.fichier().equals(m.fichier())).count();
                sb.append("    ").append(ids.get(m.id())).append("[\"").append(libelle(m))
                        .append("<br/>CCN ").append(m.complexite()).append(" · ").append(nbConstats)
                        .append(" constat(s)\"]\n");
            }
        }
        sb.append("  end\n");
        for (Methode m : faits.methodes()) {
            if (!m.cible()) {
                sb.append("  ").append(ids.get(m.id())).append("[\"").append(libelle(m)).append("\"]\n");
            }
        }
        int i = 0;
        for (PointEntree pe : faits.pointsEntree()) {
            String id = "e" + i++;
            sb.append("  ").append(id).append("([\"").append(pe.verbe()).append(' ').append(pe.chemin())
                    .append("\"]) --> ").append(ids.get(pe.methode())).append('\n');
        }
        Set<String> aretes = new LinkedHashSet<>();
        for (Appel a : faits.appels()) {
            if (ids.containsKey(a.appelant()) && ids.containsKey(a.appele()) && !a.appelant().equals(a.appele())) {
                aretes.add("  " + ids.get(a.appelant()) + " -->|\"l." + a.ligne() + "\"| " + ids.get(a.appele()));
            }
        }
        aretes.forEach(a -> sb.append(a).append('\n'));
        String idsCibles = faits.methodes().stream().filter(Methode::cible).map(m -> ids.get(m.id()))
                .collect(Collectors.joining(","));
        sb.append("  classDef legacy stroke:#E63946,stroke-width:2px\n");
        if (!idsCibles.isEmpty()) {
            sb.append("  class ").append(idsCibles).append(" legacy\n");
        }
        return sb.toString();
    }

    /** Dépendances de classe à classe (vue « composants »). */
    public static String dependances(Faits faits) {
        StringBuilder sb = new StringBuilder("flowchart LR\n");
        faits.dependances().forEach(d -> sb.append("  ").append(d.de()).append(" -->|\"").append(d.nbAppels())
                .append(" appel(s)\"| ").append(d.vers()).append('\n'));
        return sb.toString();
    }

    private static String libelle(Methode m) {
        return (m.classe() + "." + m.nom()).replace("\"", "'");
    }
}
