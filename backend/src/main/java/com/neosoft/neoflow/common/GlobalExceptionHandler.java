package com.neosoft.neoflow.common;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.filter.ServerHttpObservationFilter;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import jakarta.servlet.http.HttpServletRequest;

/**
 * Traduit les exceptions en réponses ProblemDetail (RFC 9457).
 */
@RestControllerAdvice
public class GlobalExceptionHandler extends ResponseEntityExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(DemandeIntrouvableException.class)
    public ProblemDetail demandeIntrouvable(DemandeIntrouvableException ex) {
        return probleme(HttpStatus.NOT_FOUND, "Demande introuvable", ex.getMessage());
    }

    @ExceptionHandler(TransitionInvalideException.class)
    public ProblemDetail transitionInvalide(TransitionInvalideException ex) {
        log.warn(ex.getMessage());
        return probleme(HttpStatus.CONFLICT, "Transition de statut invalide", ex.getMessage());
    }

    @ExceptionHandler(RegleMetierException.class)
    public ProblemDetail regleMetier(RegleMetierException ex) {
        ProblemDetail pd = probleme(HttpStatus.UNPROCESSABLE_ENTITY, "Règles métier non respectées",
                "La demande ne respecte pas les règles métier.");
        pd.setProperty("erreurs", ex.getErreurs());
        return pd;
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ProblemDetail accesRefuse(AccessDeniedException ex) {
        return probleme(HttpStatus.FORBIDDEN, "Accès refusé", ex.getMessage());
    }

    @ExceptionHandler(Exception.class)
    public ProblemDetail erreurInattendue(Exception ex, HttpServletRequest requete) {
        ServerHttpObservationFilter.findObservationContext(requete).ifPresent(contexte -> contexte.setError(ex));
        log.error("Erreur inattendue sur {} {}", requete.getMethod(), requete.getRequestURI(), ex);
        ProblemDetail pd = probleme(HttpStatus.INTERNAL_SERVER_ERROR, "Erreur interne",
                "Une erreur inattendue est survenue. Communiquez le traceId au support.");
        String traceId = MDC.get("traceId");
        if (traceId != null) {
            pd.setProperty("traceId", traceId);
        }
        return pd;
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(MethodArgumentNotValidException ex,
            HttpHeaders headers, HttpStatusCode status, WebRequest request) {
        List<String> erreurs = ex.getBindingResult().getFieldErrors().stream()
                .map(erreur -> erreur.getField() + " : " + erreur.getDefaultMessage())
                .sorted()
                .toList();
        ProblemDetail pd = probleme(HttpStatus.BAD_REQUEST, "Requête invalide", "Certains champs sont invalides.");
        pd.setProperty("erreurs", erreurs);
        return handleExceptionInternal(ex, pd, headers, status, request);
    }

    private static ProblemDetail probleme(HttpStatus statut, String titre, String detail) {
        ProblemDetail pd = ProblemDetail.forStatusAndDetail(statut, detail);
        pd.setTitle(titre);
        return pd;
    }
}
