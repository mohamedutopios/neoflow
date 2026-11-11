package com.neosoft.neoflow.demande;

import java.time.Clock;
import java.time.LocalDateTime;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.neosoft.neoflow.collaborateur.Collaborateur;
import com.neosoft.neoflow.collaborateur.CollaborateurRepository;
import com.neosoft.neoflow.common.DemandeIntrouvableException;
import com.neosoft.neoflow.common.RegleMetierException;
import com.neosoft.neoflow.common.TransitionInvalideException;
import com.neosoft.neoflow.demande.dto.DemandeRequest;
import com.neosoft.neoflow.demande.dto.DemandeResponse;
import com.neosoft.neoflow.demande.dto.EvenementResponse;
import com.neosoft.neoflow.notification.NotificationService;
import com.neosoft.neoflow.regles.RegleMetierRegistry;
import com.neosoft.neoflow.validation.CircuitValidationService;

/**
 * Cas d'usage des demandes : création, modification, circuit de validation et journal d'audit.
 */
@Service
@Transactional
public class DemandeService {

    private static final Logger log = LoggerFactory.getLogger(DemandeService.class);

    /** Les demandes les plus récentes d'abord. */
    private static final Sort TRI = Sort.by(Sort.Order.desc("dateCreation"), Sort.Order.desc("id"));

    private final DemandeRepository demandeRepository;
    private final EvenementDemandeRepository evenementRepository;
    private final CollaborateurRepository collaborateurRepository;
    private final CircuitValidationService circuitValidationService;
    private final RegleMetierRegistry regleMetierRegistry;
    private final NotificationService notificationService;
    private final DemandeMapper mapper;
    private final Clock horloge;

    public DemandeService(DemandeRepository demandeRepository,
            EvenementDemandeRepository evenementRepository,
            CollaborateurRepository collaborateurRepository,
            CircuitValidationService circuitValidationService,
            RegleMetierRegistry regleMetierRegistry,
            NotificationService notificationService,
            DemandeMapper mapper,
            Clock horloge) {
        this.demandeRepository = demandeRepository;
        this.evenementRepository = evenementRepository;
        this.collaborateurRepository = collaborateurRepository;
        this.circuitValidationService = circuitValidationService;
        this.regleMetierRegistry = regleMetierRegistry;
        this.notificationService = notificationService;
        this.mapper = mapper;
        this.horloge = horloge;
    }

    /**
     * Liste paginée, filtrée par statut et type (filtres facultatifs).
     *
     * @param page numéro de page, la première page est 0
     * @param size taille de page
     */
    @Transactional(readOnly = true)
    public Page<DemandeResponse> lister(StatutDemande statut, TypeDemande type, int page, int size) {
        PageRequest pageRequest = PageRequest.of(page, size, TRI);
        return demandeRepository.findAll(DemandeRepository.avecFiltres(statut, type), pageRequest)
                .map(mapper::versResponse);
    }

    @Transactional(readOnly = true)
    public DemandeResponse obtenir(Long id) {
        return mapper.versResponse(charger(id));
    }

    public DemandeResponse creer(DemandeRequest requete, String login) {
        Demande demande = new Demande();
        mapper.appliquer(requete, demande);
        completerDepartement(demande, login);
        demande.setDemandeur(login);
        demande.setStatut(StatutDemande.BROUILLON);
        LocalDateTime maintenant = LocalDateTime.now(horloge);
        demande.setDateCreation(maintenant);
        demande.setDateMaj(maintenant);
        verifierRegles(demande);

        Demande enregistree = demandeRepository.save(demande);
        tracer(enregistree, TypeEvenement.CREATION, login, null);
        log.info("Demande {} créée par {} (type {})", enregistree.getId(), login, enregistree.getType());
        return mapper.versResponse(enregistree);
    }

    public DemandeResponse modifier(Long id, DemandeRequest requete, String login) {
        Demande demande = charger(id);
        verifierDemandeur(demande, login);
        if (demande.getStatut() != StatutDemande.BROUILLON) {
            throw new TransitionInvalideException(
                    "La demande " + id + " n'est plus modifiable (statut " + demande.getStatut() + ")");
        }
        mapper.appliquer(requete, demande);
        completerDepartement(demande, login);
        demande.setDateMaj(LocalDateTime.now(horloge));
        verifierRegles(demande);
        log.info("Demande {} modifiée par {}", id, login);
        return mapper.versResponse(demande);
    }

    /**
     * Soumet la demande au circuit de validation : calcule son niveau puis applique les règles métier.
     */
    public DemandeResponse soumettre(Long id, String login) {
        Demande demande = charger(id);
        verifierDemandeur(demande, login);
        demande.changerStatut(StatutDemande.SOUMISE);
        int anciennete = circuitValidationService.ancienneteMois(demande.getDemandeur());
        int niveau = circuitValidationService.calculerNiveau(demande, anciennete);
        demande.setNiveauValidation(niveau);
        demande.setDateMaj(LocalDateTime.now(horloge));
        verifierRegles(demande);

        tracer(demande, TypeEvenement.SOUMISSION, login, "Niveau de validation " + niveau);
        log.info("Demande {} soumise par {} (niveau {})", id, login, niveau);
        return mapper.versResponse(demande);
    }

    public DemandeResponse valider(Long id, String login) {
        Demande demande = charger(id);
        demande.changerStatut(StatutDemande.VALIDEE);
        demande.setDateMaj(LocalDateTime.now(horloge));
        tracer(demande, TypeEvenement.VALIDATION, login, null);
        log.info("Demande {} validée par {}", id, login);
        notificationService.notifier(demande.getDemandeur(), "Demande validée", demande.getTitre());
        return mapper.versResponse(demande);
    }

    public DemandeResponse refuser(Long id, String motif, String login) {
        Demande demande = charger(id);
        demande.changerStatut(StatutDemande.REFUSEE);
        demande.setMotifRefus(motif);
        demande.setDateMaj(LocalDateTime.now(horloge));
        tracer(demande, TypeEvenement.REFUS, login, motif);
        log.info("Demande {} refusée par {}", id, login);
        notificationService.notifier(demande.getDemandeur(), "Demande refusée", demande.getTitre() + " : " + motif);
        return mapper.versResponse(demande);
    }

    public DemandeResponse cloturer(Long id, String login) {
        Demande demande = charger(id);
        demande.changerStatut(StatutDemande.CLOTUREE);
        demande.setDateMaj(LocalDateTime.now(horloge));
        tracer(demande, TypeEvenement.CLOTURE, login, null);
        log.info("Demande {} clôturée par {}", id, login);
        return mapper.versResponse(demande);
    }

    @Transactional(readOnly = true)
    public List<EvenementResponse> evenements(Long id) {
        if (!demandeRepository.existsById(id)) {
            throw new DemandeIntrouvableException(id);
        }
        return evenementRepository.findByDemandeIdOrderByHorodatageAscIdAsc(id).stream()
                .map(mapper::versResponse)
                .toList();
    }

    private Demande charger(Long id) {
        return demandeRepository.findById(id).orElseThrow(() -> new DemandeIntrouvableException(id));
    }

    private void verifierDemandeur(Demande demande, String login) {
        if (!demande.getDemandeur().equals(login)) {
            throw new AccessDeniedException("Seul le demandeur peut modifier ou soumettre la demande " + demande.getId());
        }
    }

    private void completerDepartement(Demande demande, String login) {
        if (demande.getDepartement() == null) {
            demande.setDepartement(collaborateurRepository.findById(login)
                    .map(Collaborateur::getDepartement)
                    .orElse(null));
        }
    }

    private void verifierRegles(Demande demande) {
        List<String> erreurs = regleMetierRegistry.verifier(demande);
        if (!erreurs.isEmpty()) {
            throw new RegleMetierException(erreurs);
        }
    }

    private void tracer(Demande demande, TypeEvenement type, String auteur, String commentaire) {
        evenementRepository.save(new EvenementDemande(demande, type, auteur, LocalDateTime.now(horloge), commentaire));
    }
}
