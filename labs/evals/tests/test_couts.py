from conftest import LAB
from couts import charger_tarifs, cout

TARIFS = charger_tarifs(LAB / "mesure" / "exemples" / "tarifs_fictifs.yaml")


def test_formule():
    usage = {"claude-sonnet-5-5": {"input_tokens": 1_000_000, "output_tokens": 1_000_000,
                                   "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000}}
    total, detail, manquants = cout(usage, TARIFS)
    assert manquants == [] and total == 1.0 + 5.0 + 0.10 + 1.25 == detail["claude-sonnet-5-5"]


def test_suffixe_de_version_et_prefixe_fournisseur():
    total, _, _ = cout({"anthropic/claude-opus-5-5-20261101": {"input_tokens": 500_000}}, TARIFS)
    assert total == 1.0


def test_prix_manquant_donne_none():
    total, _, manquants = cout({"claude-inconnu": {"input_tokens": 10}}, TARIFS)
    assert total is None and manquants
    vide = charger_tarifs(LAB / "mesure" / "tarifs.example.yaml")
    total, _, manquants = cout({"claude-sonnet-5-5": {"input_tokens": 10}}, vide)
    assert total is None and "claude-sonnet-5-5.input" in manquants


def test_modele_simule_et_ecriture_du_cache():
    total, detail, manquants = cout({"simule:claude-sonnet-5-5": {"input_tokens": 10_000}}, TARIFS)
    assert total == 0.0 and not manquants
    total, _, _ = cout({"claude-sonnet-5-5": {"cache_creation_input_tokens": 2_000_000}}, TARIFS)
    assert total == 2.5                       # écriture du cache comptée à son propre prix (variable cache_write)
