package com.neosoft.neoflow.demande;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.security.access.AccessDeniedException;

import com.neosoft.neoflow.collaborateur.Collaborateur;
import com.neosoft.neoflow.collaborateur.CollaborateurRepository;
import com.neosoft.neoflow.common.DemandeIntrouvableException;
import com.neosoft.neoflow.common.RegleMetierException;
import com.neosoft.neoflow.common.TransitionInvalideException;
import com.neosoft.neoflow.demande.dto.DemandeRequest;
import com.neosoft.neoflow.demande.dto.DemandeResponse;
import com.neosoft.neoflow.notification.NotificationService;
import com.neosoft.neoflow.regles.RegleMetierRegistry;
import com.neosoft.neoflow.validation.CircuitValidationService;

@ExtendWith(MockitoExtension.class)
class DemandeServiceTest {

    private static final Clock HORLOGE = Clock.fixed(Instant.parse("2026-11-04T09:00:00Z"), ZoneId.of("Europe/Paris"));

    @Mock
    private DemandeRepository demandeRepository;
    @Mock
    private EvenementDemandeRepository evenementRepository;
    @Mock
    private CollaborateurRepository collaborateurRepository;
    @Mock
    private CircuitValidationService circuitValidationService;
    @Mock
    private RegleMetierRegistry regleMetierRegistry;
    @Mock
    private NotificationService notificationService;

    private DemandeService service;

    @BeforeEach
    void initialiser() {
        service = new DemandeService(demandeRepository, evenementRepository, collaborateurRepository,
                circuitValidationService, regleMetierRegistry, notificationService, new DemandeMapper(), HORLOGE);
    }

    @Test
    void creer_enregistreLaDemandeEnBrouillonAvecLeDepartementDuCollaborateur() {
        when(collaborateurRepository.findById("alice")).thenReturn(Optional.of(
                new Collaborateur("alice", "Alice Martin", "COMMERCIAL", LocalDate.of(2021, 3, 15))));
        when(regleMetierRegistry.verifier(any())).thenReturn(List.of());
        when(demandeRepository.save(any(Demande.class))).thenAnswer(invocation -> {
            Demande d = invocation.getArgument(0);
            d.setId(42L);
            return d;
        });

        DemandeResponse reponse = service.creer(requete(TypeDemande.NOTE_DE_FRAIS, new BigDecimal("86.40")), "alice");

        assertThat(reponse.id()).isEqualTo(42L);
        assertThat(reponse.statut()).isEqualTo(StatutDemande.BROUILLON);
        assertThat(reponse.demandeur()).isEqualTo("alice");
        assertThat(reponse.departement()).isEqualTo("COMMERCIAL");
        assertThat(reponse.dateCreation()).isEqualTo(LocalDateTime.now(HORLOGE));
        assertThat(evenementEnregistre().getType()).isEqualTo(TypeEvenement.CREATION);
    }

    @Test
    void creer_refuseLaDemandeQuandUneRegleMetierEchoue() {
        when(collaborateurRepository.findById("alice")).thenReturn(Optional.empty());
        when(regleMetierRegistry.verifier(any())).thenReturn(List.of("Le montant est trop élevé"));

        assertThatThrownBy(() -> service.creer(requete(TypeDemande.ACHAT, new BigDecimal("99999")), "alice"))
                .isInstanceOf(RegleMetierException.class)
                .satisfies(ex -> assertThat(((RegleMetierException) ex).getErreurs())
                        .containsExactly("Le montant est trop élevé"));
        verify(demandeRepository, never()).save(any());
    }

    @Test
    void soumettre_passeLaDemandeAuStatutSoumiseEtTraceLEvenement() {
        Demande demande = demande(StatutDemande.BROUILLON, new BigDecimal("120.00"));
        when(demandeRepository.findById(7L)).thenReturn(Optional.of(demande));
        when(circuitValidationService.ancienneteMois("alice")).thenReturn(60);
        when(circuitValidationService.calculerNiveau(any(Demande.class), anyInt())).thenReturn(1);
        when(regleMetierRegistry.verifier(any())).thenReturn(List.of());

        DemandeResponse reponse = service.soumettre(7L, "alice");

        assertThat(reponse.statut()).isEqualTo(StatutDemande.SOUMISE);
        verify(circuitValidationService).calculerNiveau(eq(demande), eq(60));
        assertThat(evenementEnregistre().getType()).isEqualTo(TypeEvenement.SOUMISSION);
    }

    @Test
    void soumettre_estReserveAuDemandeur() {
        when(demandeRepository.findById(7L)).thenReturn(Optional.of(demande(StatutDemande.BROUILLON, BigDecimal.TEN)));

        assertThatThrownBy(() -> service.soumettre(7L, "mallory")).isInstanceOf(AccessDeniedException.class);
        verify(circuitValidationService, never()).calculerNiveau(any(), anyInt());
    }

    @Test
    void valider_refuseUneDemandeEncoreEnBrouillon() {
        when(demandeRepository.findById(7L)).thenReturn(Optional.of(demande(StatutDemande.BROUILLON, BigDecimal.TEN)));

        assertThatThrownBy(() -> service.valider(7L, "bob")).isInstanceOf(TransitionInvalideException.class);
        verify(evenementRepository, never()).save(any());
    }

    @Test
    void refuser_enregistreLeMotifEtPrevientLeDemandeur() {
        Demande demande = demande(StatutDemande.SOUMISE, new BigDecimal("1250.00"));
        when(demandeRepository.findById(7L)).thenReturn(Optional.of(demande));

        DemandeResponse reponse = service.refuser(7L, "Hors budget", "bob");

        assertThat(reponse.statut()).isEqualTo(StatutDemande.REFUSEE);
        assertThat(reponse.motifRefus()).isEqualTo("Hors budget");
        EvenementDemande evenement = evenementEnregistre();
        assertThat(evenement.getType()).isEqualTo(TypeEvenement.REFUS);
        assertThat(evenement.getAuteur()).isEqualTo("bob");
        assertThat(evenement.getCommentaire()).isEqualTo("Hors budget");
        verify(notificationService).notifier(eq("alice"), any(), any());
    }

    @Test
    void cloturer_refuseUneDemandeRefusee() {
        when(demandeRepository.findById(7L)).thenReturn(Optional.of(demande(StatutDemande.REFUSEE, BigDecimal.TEN)));

        assertThatThrownBy(() -> service.cloturer(7L, "admin")).isInstanceOf(TransitionInvalideException.class);
    }

    @Test
    void modifier_refuseUneDemandeDejaSoumise() {
        when(demandeRepository.findById(7L)).thenReturn(Optional.of(demande(StatutDemande.SOUMISE, BigDecimal.TEN)));

        assertThatThrownBy(() -> service.modifier(7L, requete(TypeDemande.NOTE_DE_FRAIS, BigDecimal.ONE), "alice"))
                .isInstanceOf(TransitionInvalideException.class);
    }

    @Test
    void obtenir_signaleUneDemandeInexistante() {
        when(demandeRepository.findById(404L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.obtenir(404L)).isInstanceOf(DemandeIntrouvableException.class);
    }

    @Test
    @SuppressWarnings("unchecked")
    void lister_demandeLaPremierePageTrieeParDateDeCreationDecroissante() {
        Page<Demande> page = new PageImpl<>(List.of(demande(StatutDemande.SOUMISE, BigDecimal.TEN)));
        when(demandeRepository.findAll(any(Specification.class), any(Pageable.class))).thenReturn(page);

        Page<DemandeResponse> resultat = service.lister(null, null, 0, 20);

        ArgumentCaptor<Pageable> pageable = ArgumentCaptor.forClass(Pageable.class);
        verify(demandeRepository).findAll(any(Specification.class), pageable.capture());
        assertThat(pageable.getValue().getPageNumber()).isZero();
        assertThat(pageable.getValue().getPageSize()).isEqualTo(20);
        assertThat(pageable.getValue().getSort().getOrderFor("dateCreation").getDirection())
                .isEqualTo(Sort.Direction.DESC);
        assertThat(resultat.getContent()).hasSize(1);
    }

    private EvenementDemande evenementEnregistre() {
        ArgumentCaptor<EvenementDemande> captor = ArgumentCaptor.forClass(EvenementDemande.class);
        verify(evenementRepository).save(captor.capture());
        return captor.getValue();
    }

    private static DemandeRequest requete(TypeDemande type, BigDecimal montant) {
        return new DemandeRequest(type, "Déplacement client", "Train aller-retour", montant,
                LocalDate.of(2026, 11, 10), null, null, false);
    }

    private static Demande demande(StatutDemande statut, BigDecimal montant) {
        Demande d = new Demande();
        d.setId(7L);
        d.setType(TypeDemande.NOTE_DE_FRAIS);
        d.setTitre("Déjeuner client");
        d.setDemandeur("alice");
        d.setMontant(montant);
        d.setDateDebut(LocalDate.of(2026, 10, 8));
        d.setStatut(statut);
        d.setDepartement("COMMERCIAL");
        d.setDateCreation(LocalDateTime.of(2026, 10, 8, 18, 0));
        d.setDateMaj(LocalDateTime.of(2026, 10, 8, 18, 0));
        return d;
    }
}
