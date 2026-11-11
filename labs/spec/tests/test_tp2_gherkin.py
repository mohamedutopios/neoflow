"""TP 2 — validation des scénarios Gherkin."""
from __future__ import annotations

from pathlib import Path

from neospec.validation import Rapport
from neospec.validation.gherkin import valider_features

EXIGENCES = {f"EF-{i:02d}": "" for i in range(1, 17)} | {f"ENF-{i:02d}": "" for i in range(1, 9)}

BON = """# language: fr
@conges @api
Fonctionnalité: Exemple
  Contexte:
    Étant donné que la date du jour est le "2026-11-16"

  @EF-01
  Règle: Une règle

    Scénario: Cas nominal
      Quand "alice" crée une demande de congés CP du "2026-12-21" au "2026-12-24"
      Alors la demande est créée au statut "BROUILLON"
"""


def _valider(tmp_path: Path, texte: str, exigences=EXIGENCES):
    f = tmp_path / "x.feature"
    f.write_text(texte, encoding="utf-8")
    r = Rapport()
    return valider_features([f], exigences, r), r


def test_fixture_conges_valide(tmp_path, fixture_generation):
    fichiers = []
    for f in fixture_generation["features"]:
        p = tmp_path / f["fichier"]
        p.write_text(f["contenu"], encoding="utf-8")
        fichiers.append(p)
    r = Rapport()
    couverture = valider_features(fichiers, EXIGENCES, r)
    assert r.erreurs == [] and r.avertissements == []
    assert all(couverture.get(f"EF-{i:02d}", 0) > 0 for i in range(1, 17))
    assert couverture["EF-09"] == 7


def test_scenario_bien_forme(tmp_path):
    couverture, r = _valider(tmp_path, BON)
    assert r.ok and couverture == {"EF-01": 1}


def test_en_tete_de_langue(tmp_path):
    _, r = _valider(tmp_path, BON.replace("# language: fr\n", ""))
    assert any("language" in e for e in r.erreurs)
    assert any("syntaxe" in e for e in r.erreurs)


def test_etiquette_inconnue_ou_absente(tmp_path):
    _, r = _valider(tmp_path, BON.replace("@EF-01", "@EF-99"))
    assert any("@EF-99 inconnue" in e for e in r.erreurs)
    _, r = _valider(tmp_path, BON.replace("  @EF-01\n", ""))
    assert any("aucune étiquette d'exigence" in e for e in r.erreurs)


def test_heritage_depuis_la_fonctionnalite(tmp_path):
    couverture, r = _valider(tmp_path, BON.replace("@conges @api", "@conges @api @EF-02").replace("  @EF-01\n", ""))
    assert r.ok and couverture == {"EF-02": 1}


def test_sans_alors_et_actions_multiples(tmp_path):
    _, r = _valider(tmp_path, BON.replace('      Alors la demande est créée au statut "BROUILLON"\n', ""))
    assert any("aucune étape « Alors »" in e for e in r.erreurs)
    texte = BON + '      Quand "alice" soumet ce brouillon\n      Alors la demande est soumise\n'
    _, r = _valider(tmp_path, texte)
    assert r.ok and any("2 actions" in a for a in r.avertissements) and any("après un résultat" in a for a in r.avertissements)


def test_plan_sans_exemples(tmp_path):
    texte = BON.replace("Scénario: Cas nominal", "Plan du scénario: Cas <x>") + "\n      Exemples:\n        | x |\n"
    _, r = _valider(tmp_path, texte)
    assert any("sans ligne d'exemples" in e for e in r.erreurs)
