"""TP 3 — validation du contrat delta OpenAPI."""
from __future__ import annotations

import re

from neospec.validation import Rapport
from neospec.validation.openapi import valider_contrat

EXIGENCES = {f"EF-{i:02d}": "" for i in range(1, 17)} | {f"ENF-{i:02d}": "" for i in range(1, 9)}


def _valider(tmp_path, texte):
    f = tmp_path / "delta.yaml"
    f.write_text(texte, encoding="utf-8")
    r = Rapport()
    return valider_contrat(f, EXIGENCES, r), r


def test_contrat_conges_valide(tmp_path, fixture_generation):
    cites, r = _valider(tmp_path, fixture_generation["openapi_delta"])
    assert r.erreurs == [] and r.avertissements == []
    assert "EF-14" in cites and "ENF-02" in cites


def test_operation_id_absent(tmp_path, fixture_generation):
    texte = fixture_generation["openapi_delta"].replace("      operationId: simulerDecompteConges\n", "", 1)
    _, r = _valider(tmp_path, texte)
    assert any("operationId absent" in e and "/api/conges/decompte" in e for e in r.erreurs)


def test_sans_reponse_4xx(tmp_path, fixture_generation):
    texte = re.sub(r"        '400':\n          \$ref: '#/components/responses/RequeteInvalide'\n        '401':\n          \$ref: '#/components/responses/NonAuthentifie'\ncomponents:",
                   "components:", fixture_generation["openapi_delta"])
    _, r = _valider(tmp_path, texte)
    assert any("aucune réponse 4xx" in e for e in r.erreurs)


def test_exigence_inconnue_et_absente(tmp_path, fixture_generation):
    _, r = _valider(tmp_path, fixture_generation["openapi_delta"].replace("x-exigences: [EF-14, ENF-01, ENF-03]", "x-exigences: [EF-99]"))
    assert any("EF-99" in e for e in r.erreurs)
    _, r = _valider(tmp_path, fixture_generation["openapi_delta"].replace("      x-exigences: [EF-14, ENF-01, ENF-03]\n", ""))
    assert r.ok and any("x-exigences absent" in a for a in r.avertissements)


def test_document_invalide(tmp_path, fixture_generation):
    _, r = _valider(tmp_path, fixture_generation["openapi_delta"].replace("openapi: 3.1.0", "openapi: 3.1.0\nfoo: bar"))
    assert any("contrat OpenAPI invalide" in e for e in r.erreurs)
    _, r = _valider(tmp_path, "openapi: [3.1\n  :")
    assert any("YAML illisible" in e for e in r.erreurs)


def test_etiquette_non_declaree(tmp_path, fixture_generation):
    _, r = _valider(tmp_path, fixture_generation["openapi_delta"].replace("tags: [Conges]", "tags: [Inconnue]", 1))
    assert any("« Inconnue » non déclarée" in e for e in r.erreurs)


def test_exemple_non_conforme(tmp_path, fixture_generation):
    texte = fixture_generation["openapi_delta"].replace("                    sousType: CP\n                    demiJourneeDebut: true",
                                                        "                    sousType: CONGE_PAYE\n                    demiJourneeDebut: true", 1)
    _, r = _valider(tmp_path, texte)
    assert any("exemple non conforme" in e and "CONGE_PAYE" in e for e in r.erreurs)
