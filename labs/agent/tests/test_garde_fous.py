from __future__ import annotations

import os
from pathlib import Path

import pytest

from neoagent.garde_fous import Politique, RefusGardeFou


class TestChemins:
    def test_chemin_relatif_resolu_dans_le_worktree(self, depot: Path):
        assert Politique.lecture(depot).resoudre("docs/specs/CONGES.md") == (depot / "docs/specs/CONGES.md").resolve()

    @pytest.mark.parametrize("chemin", ["../autre/secret.txt", "/etc/passwd", "backend/../../hors.txt"])
    def test_refus_hors_worktree(self, depot: Path, chemin: str):
        with pytest.raises(RefusGardeFou, match="hors du worktree"):
            Politique.lecture(depot).resoudre(chemin)

    def test_lien_symbolique_vers_l_exterieur_refuse(self, depot: Path, tmp_path: Path):
        (tmp_path / "dehors.txt").write_text("secret")
        (depot / "lien.txt").symlink_to(tmp_path / "dehors.txt")
        with pytest.raises(RefusGardeFou, match="hors du worktree"):
            Politique.lecture(depot).resoudre("lien.txt")

    @pytest.mark.parametrize("chemin", [".env", ".git/config", "backend/.env.local", "config/secrets/cle.txt"])
    def test_chemins_interdits_meme_en_lecture(self, depot: Path, chemin: str):
        with pytest.raises(RefusGardeFou, match="interdit"):
            Politique.lecture(depot).resoudre(chemin)


class TestEcriture:
    def test_lecture_seule_par_defaut(self, depot: Path):
        politique = Politique(racine=depot)
        assert politique.lecture_seule
        with pytest.raises(RefusGardeFou, match="lecture seule"):
            politique.verifier_ecriture("backend/src/main/java/com/neosoft/neoflow/conges/RegleConges.java")

    def test_generateur_ecrit_le_code_de_production(self, depot: Path):
        cible = Politique.generateur(depot).verifier_ecriture("backend/src/main/java/com/neosoft/neoflow/conges/Neuf.java")
        assert cible.name == "Neuf.java"

    @pytest.mark.parametrize("chemin", [
        "backend/src/test/java/com/neosoft/neoflow/conges/RegleCongesTest.java",
        "frontend/src/pages/DemandeFormulaire.conges.test.tsx",
        "docs/specs/CONGES.md",
        "backend/src/main/java/com/neosoft/neoflow/legacy/RegleValidationLegacy.java",
        "backend/pom.xml",
    ])
    def test_generateur_ne_touche_ni_tests_ni_spec_ni_legacy_ni_dependances(self, depot: Path, chemin: str):
        with pytest.raises(RefusGardeFou, match="protégé"):
            Politique.generateur(depot).verifier_ecriture(chemin)

    def test_perimetre_d_un_worker(self, depot: Path):
        politique = Politique.generateur(depot, chemins_ecriture=("frontend/*",))
        politique.verifier_ecriture("frontend/src/api/conges.ts")
        with pytest.raises(RefusGardeFou, match="périmètre"):
            politique.verifier_ecriture("backend/src/main/java/X.java")

    def test_redacteur_de_tests_n_ecrit_que_des_tests(self, depot: Path):
        politique = Politique.redacteur_tests(depot)
        politique.verifier_ecriture("backend/src/test/java/com/neosoft/neoflow/conges/NouveauTest.java")
        with pytest.raises(RefusGardeFou):
            politique.verifier_ecriture("backend/src/main/java/com/neosoft/neoflow/conges/RegleConges.java")


class TestCommandes:
    def test_allowlist_par_prefixe(self, depot: Path):
        argv, cwd = Politique.generateur(depot).verifier_commande("./mvnw -q test -Dtest=RegleCongesTest", "backend")
        assert argv == ["./mvnw", "-q", "test", "-Dtest=RegleCongesTest"]
        assert cwd == (depot / "backend").resolve()

    @pytest.mark.parametrize("commande", ["rm -rf /", "curl https://exemple.test", "git push origin main",
                                          "python -c 'import os'", "npm install left-pad"])
    def test_refus_hors_allowlist(self, depot: Path, commande: str):
        with pytest.raises(RefusGardeFou, match="hors allowlist"):
            Politique.generateur(depot).verifier_commande(commande)

    @pytest.mark.parametrize("commande", ["git status; rm -rf ~", "./mvnw test && curl x", "git diff > /tmp/x",
                                          "git log $(whoami)", "npm test | tee log"])
    def test_refus_operateurs_de_shell(self, depot: Path, commande: str):
        with pytest.raises(RefusGardeFou, match="opérateur"):
            Politique.generateur(depot).verifier_commande(commande)

    def test_refus_argument_dangereux(self, depot: Path):
        with pytest.raises(RefusGardeFou, match="argument"):
            Politique.lecture(depot).verifier_commande("git diff --output=/tmp/vol.txt")

    def test_lecture_seule_n_autorise_que_git_en_lecture(self, depot: Path):
        politique = Politique.lecture(depot)
        politique.verifier_commande("git status")
        with pytest.raises(RefusGardeFou, match="lecture seule"):
            politique.verifier_commande("./mvnw -q test")

    def test_repertoire_hors_worktree_refuse(self, depot: Path):
        with pytest.raises(RefusGardeFou, match="hors du worktree"):
            Politique.generateur(depot).verifier_commande("git status", "../..")

    def test_environnement_sans_secrets(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-faux")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_faux")
        monkeypatch.setenv("NEOFLOW_PROFIL", "test")
        env = Politique.environnement()
        assert "ANTHROPIC_API_KEY" not in env and "GITHUB_TOKEN" not in env
        assert env["NEOFLOW_PROFIL"] == "test" and env["PATH"] == os.environ["PATH"]
