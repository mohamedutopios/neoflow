import json

import controles_qualite as cq


def test_simulation_et_mesures(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "mvnw").write_text("")
    cfg = tmp_path / "c.yaml"
    cfg.write_text("controles:\n"
                   "  - {nom: ok, commande: 'true'}\n"
                   "  - {nom: ko, commande: 'false'}\n"
                   "  - {nom: compte, type: mesure, commande: 'echo 4'}\n"
                   "  - {nom: absent, commande: 'x', outil: outil-qui-nexiste-pas}\n"
                   "  - {nom: requis, commande: 'true', requiert: backend/mvnw}\n")
    sortie = tmp_path / "r.json"
    assert cq.main(["--racine", str(tmp_path), "--config", str(cfg), "--sortie", str(sortie)]) == 1
    statuts = {c["nom"]: (c["statut"], c.get("valeur")) for c in json.loads(sortie.read_text())["controles"]}
    assert statuts == {"ok": ("OK", None), "ko": ("KO", None), "compte": ("MESURE", 4), "absent": ("ABSENT", None),
                       "requis": ("OK", None)}
    assert cq.main(["--racine", str(tmp_path), "--config", str(cfg), "-n", "--sortie", str(sortie)]) == 0
