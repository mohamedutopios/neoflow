package exemple;

/** Cible minimale des tests du lab : conversion du paramètre « page » de l'API (0-based) en index Spring Data. */
public class Pagination {

    public static int index(int page) {
        if (page < 0) {
            throw new IllegalArgumentException("page négative : " + page);
        }
        return page;
    }
}
