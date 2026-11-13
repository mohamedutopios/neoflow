import jakarta.persistence.EntityManager;
import org.apache.commons.text.StringSubstitutor;

class Exemples {
    EntityManager em;

    Object f1(String q) {
        // ruleid: neoflow-requete-native-concatenee
        return em.createNativeQuery("SELECT * FROM demande WHERE titre LIKE '%" + q + "%'", Demande.class).getResultList();
    }

    Object f1bis(String q) {
        // ruleid: neoflow-requete-native-concatenee
        String sql = "SELECT * FROM demande WHERE titre = '" + q + "'";
        return em.createNativeQuery(sql, Demande.class).getResultList();
    }

    Object f1format(String q) {
        // ruleid: neoflow-requete-native-concatenee
        return em.createQuery(String.format("from Demande where titre = '%s'", q)).getResultList();
    }

    Object ok(String q) {
        // ok: neoflow-requete-native-concatenee
        return em.createNativeQuery("SELECT * FROM demande WHERE titre LIKE :q", Demande.class)
            .setParameter("q", "%" + q + "%").getResultList();
    }

    Object okConstantes() {
        // ok: neoflow-requete-native-concatenee
        return em.createNativeQuery("SELECT * FROM demande " + "ORDER BY id", Demande.class).getResultList();
    }

    String f3(String titre) {
        // ruleid: neoflow-commons-text-interpolation
        return StringSubstitutor.createInterpolator().replace(titre);
    }

    String f3ok(java.util.Map<String, String> m) {
        // ok: neoflow-commons-text-interpolation
        return new StringSubstitutor(m).replace("${titre}");
    }

    void f5(AuthorizeHttpRequestsConfigurer<HttpSecurity>.AuthorizationManagerRequestMatcherRegistry auth) {
        // ruleid: neoflow-actuator-permitall
        auth.requestMatchers("/actuator/**").permitAll();
        // ok: neoflow-actuator-permitall
        auth.requestMatchers("/actuator/health", "/actuator/info").permitAll();
        // ok: neoflow-actuator-permitall
        auth.requestMatchers("/actuator/**").hasRole("ADMIN");
    }
}
