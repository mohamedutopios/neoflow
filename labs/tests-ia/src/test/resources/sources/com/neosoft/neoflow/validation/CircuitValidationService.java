package com.neosoft.neoflow.validation;

import java.time.Clock;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;

import org.springframework.stereotype.Service;

import com.neosoft.neoflow.collaborateur.CollaborateurRepository;
import com.neosoft.neoflow.demande.Demande;
import com.neosoft.neoflow.legacy.RegleValidationLegacy;

/**
 * Adaptateur entre le domaine NeoFlow et le module legacy de détermination du circuit de validation.
 */
@Service
public class CircuitValidationService {

    private final CollaborateurRepository collaborateurRepository;
    private final Clock horloge;

    public CircuitValidationService(CollaborateurRepository collaborateurRepository, Clock horloge) {
        this.collaborateurRepository = collaborateurRepository;
        this.horloge = horloge;
    }

    /**
     * Niveau de validation (1 à 3) de la demande, calculé par {@link RegleValidationLegacy}.
     */
    public int calculerNiveau(Demande d, int ancienneteMois) {
        Double montant = d.getMontant().doubleValue();
        return RegleValidationLegacy.determinerNiveau(d.getType().name(), montant, ancienneteMois, d.getDepartement(), d.isUrgent());
    }

    /**
     * Ancienneté du collaborateur en mois révolus, 0 s'il est absent du référentiel.
     */
    public int ancienneteMois(String login) {
        LocalDate aujourdhui = LocalDate.now(horloge);
        return collaborateurRepository.findById(login)
                .map(c -> (int) ChronoUnit.MONTHS.between(c.getDateEntree(), aujourdhui))
                .orElse(0);
    }
}
