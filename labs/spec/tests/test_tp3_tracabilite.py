"""TP 3 — matrice de traçabilité et lecture de la spécification."""
from __future__ import annotations

from neospec.validation import Rapport
from neospec.validation.tracabilite import lire_spec, verifier_matrice

EXIG = {"EF-01": "a", "EF-02": "b", "ENF-01": "c", "ENF-02": "d"}
ENTETE = "| Exigence | Règles | Scénario(s) | Contrat | Tâche(s) | Test(s) prévus | Commit(s) | Statut |\n|---|---|---|---|---|---|---|---|\n"


def _matrice(*lignes):
    return ENTETE + "\n".join(lignes) + "\n"


L_EF1 = "| EF-01 | RM-01 | f › r (1) | creer | T01 | RegleTest | — | ⏳ |"
L_EF2 = "| EF-02 | RM-02 | f › r (1) | creer | T01 | RegleTest | — | ⏳ |"
L_ENF1 = "| ENF-01 | — | — | creer | T02 | Mesure p95 (J10) | — | ⏳ |"
L_ENF2 = "| ENF-02 | — | f › s (2) | creer | T03 | — | — | ⏳ |"


def test_matrice_complete():
    r = Rapport()
    verifier_matrice(_matrice(L_EF1, L_EF2, L_ENF1, L_ENF2), EXIG, {"EF-01": 2, "EF-02": 1, "ENF-02": 2}, r)
    assert r.ok
    assert any("ENF-01 prouvée hors Gherkin : Mesure p95 (J10)" in i for i in r.infos)


def test_ligne_absente_et_inconnue():
    r = Rapport()
    verifier_matrice(_matrice(L_EF1, L_ENF1, L_ENF2, "| EF-07 | — | — | — | — | X | — | ⏳ |"), EXIG,
                     {"EF-01": 1, "EF-02": 1, "ENF-02": 1}, r)
    assert "EF-02 absente de la matrice de traçabilité" in r.erreurs
    assert "Matrice : EF-07 n'existe pas dans la spécification" in r.erreurs


def test_ef_sans_scenario_et_enf_sans_preuve():
    r = Rapport()
    verifier_matrice(_matrice(L_EF1, L_EF2, L_ENF1.replace("Mesure p95 (J10)", "—"), L_ENF2), EXIG, {"EF-01": 1, "ENF-02": 1}, r)
    assert "EF-02 n'est couverte par aucun scénario" in r.erreurs
    assert any(e.startswith("ENF-01 n'a ni scénario ni test prévu") for e in r.erreurs)


def test_matrice_absente_ou_sans_entete():
    r = Rapport()
    verifier_matrice(None, EXIG, {"EF-01": 1, "EF-02": 1}, r)
    assert "Matrice de traçabilité absente" in r.erreurs
    r = Rapport()
    verifier_matrice("\n".join([L_EF1, L_EF2]), EXIG, {"EF-01": 1, "EF-02": 1}, r)
    assert any("en-tête" in e for e in r.erreurs)


def test_identifiants_prefixes():
    texte = "| Statut | EN REVUE |\n### EF-CONGES-01 — A\n### CONG-EF-02 — B\n### ENF-CONGES-01 — C\n| H-01 | x | Validée | DRH | 2026-11-16 |\n"
    statut, exigences, attente, nb = lire_spec(texte)
    assert statut == "EN REVUE" and list(exigences) == ["EF-CONGES-01", "CONG-EF-02", "ENF-CONGES-01"]
    assert attente == [] and nb == 1
