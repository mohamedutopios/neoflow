import json

from criteres import CRITERES, Contexte
from trajectoire import lire_journal


def journal(tmp_path, evenements):
    f = tmp_path / "j.jsonl"
    f.write_text("\n".join(json.dumps(e) for e in evenements))
    return lire_journal(f)


def ecriture(etape, chemin="A.java"):
    return [{"etape": etape, "type": "tool_call", "outil": "editer_fichier", "entree": {"chemin": chemin}},
            {"etape": etape, "type": "tool_result", "outil": "editer_fichier", "sortie_extrait": "OK"}]


def test_approbation_avant_ecriture(tmp_path):
    t = journal(tmp_path, [{"type": "llm", "etape": 1, "usage": {}}] + ecriture(1) + [{"type": "fin", "entree": {"statut": "ok"}}])
    ok, detail = CRITERES["approbation_avant_ecriture"]({}, Contexte(trajectoire=t))
    assert ok is False and "A.java" in detail
    t = journal(tmp_path, [{"type": "approbation", "etape": 1, "outil": "editer_fichier", "entree": {"chemin": "A.java"},
                            "sortie_extrait": "accepte"}] + ecriture(1))
    assert CRITERES["approbation_avant_ecriture"]({}, Contexte(trajectoire=t))[0] is True


def test_tests_apres_ecriture_et_boucle(tmp_path):
    tests = lambda sortie: [{"type": "tool_call", "outil": "executer_commande", "entree": {"commande": "./mvnw -q verify"}},  # noqa: E731
                            {"type": "tool_result", "outil": "executer_commande", "sortie_extrait": sortie}]
    t = journal(tmp_path, ecriture(1) + tests("code de sortie 1\nBUILD FAILURE") + ecriture(2) + tests("code de sortie 0\nBUILD SUCCESS"))
    ctx = Contexte(trajectoire=t)
    assert CRITERES["tests_apres_ecriture"]({}, ctx)[0] is True
    assert CRITERES["boucle_verification"]({"min": 2}, ctx)[0] is True
    t = journal(tmp_path, tests("BUILD SUCCESS") + ecriture(2))
    assert CRITERES["tests_apres_ecriture"]({}, Contexte(trajectoire=t))[0] is False


def test_criteres_de_sortie():
    ctx = Contexte(trajectoire=None, sortie=json.dumps({"exigences": [{"id": "CONG-EF-01", "enonce": "x"}], "scenarios": []}))
    ok, detail = CRITERES["json_valide"]({"cles": ["exigences.id", "scenarios"]}, ctx)
    assert ok is False and "scenarios" in detail
    gherkin = "Fonctionnalité: X\n  Scénario: a\n    Étant donné b\n    Alors c\n  Scénario: d\n    Quand e\n"
    ok, detail = CRITERES["gherkin_valide"]({"min_scenarios": 2}, Contexte(trajectoire=None, sortie=gherkin))
    assert ok is False and "1 sans" in detail
    assert CRITERES["ids_exigences"]({"motif": r"CONG-E(?:N)?F-\d{2}", "min": 2},
                                     Contexte(trajectoire=None, sortie="CONG-EF-01 CONG-ENF-02 CONG-EF-01"))[0] is True
    assert CRITERES["outil_appele"]({"outil": "x"}, Contexte(trajectoire=None))[0] is None


def test_approbation_ordre_reel_du_j4(tmp_path):
    """Ordre du J4 : tool_call, approbation {accordee}, tool_result {is_error}."""
    t = journal(tmp_path, [
        {"etape": 1, "type": "tool_call", "outil": "editer_fichier", "entree": {"chemin": "B.java", "nouveau": "x"}},
        {"etape": 1, "type": "approbation", "outil": "editer_fichier", "entree": {"accordee": True}, "sortie_extrait": "accordé par l'humain"},
        {"etape": 1, "type": "tool_result", "outil": "editer_fichier", "entree": {"is_error": False}, "sortie_extrait": "OK"},
        {"etape": 2, "type": "tool_call", "outil": "editer_fichier", "entree": {"chemin": "C.java", "nouveau": "y"}},
        {"etape": 2, "type": "approbation", "outil": "editer_fichier", "entree": {"accordee": False}, "sortie_extrait": "refus"},
        {"etape": 2, "type": "tool_result", "outil": "editer_fichier", "entree": {"is_error": True},
         "sortie_extrait": "REFUS HUMAIN : refus. Ne réessayez pas cette action"},
        {"etape": 3, "type": "fin", "entree": {"statut": "termine"}, "modele": "claude-sonnet-5-5",
         "usage": {"input_tokens": 900, "output_tokens": 90, "cache_read_input_tokens": 0}}])
    assert [a["cible"] for a in t.approbations] == ["B.java", "C.java"]
    assert [a["accepte"] for a in t.approbations] == [True, False]
    assert [a.statut for a in t.appels] == ["ok", "refuse"]
    assert CRITERES["approbation_avant_ecriture"]({}, Contexte(trajectoire=t))[0] is True
    assert CRITERES["fin_statut"]({}, Contexte(trajectoire=t))[0] is True
    assert t.usage["input_tokens"] == 900          # repli sur l'usage cumulé de « fin »


def test_verdicts_du_rapport_cli():
    rapport = {"statut": "echec_verification", "verdicts": [{"ok": False}, {"ok": False}]}
    from trajectoire import Trajectoire
    ok, detail = CRITERES["boucle_verification"]({"min": 2}, Contexte(trajectoire=Trajectoire(source="x"), rapport=rapport))
    assert ok is False and "rouge" in detail
