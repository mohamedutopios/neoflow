"""Étape 5 — scénarios Gherkin → squelettes de step definitions Cucumber-JVM (Java).

Une méthode par formulation d'étape distincte, quelle que soit la fonctionnalité qui l'utilise
(Cucumber refuse deux définitions pour la même expression). Les valeurs concrètes deviennent
des paramètres : texte entre guillemets → {string}, entier → {int}, décimal à virgule →
{decimal} (type déclaré), alternatives déclarées dans un fichier YAML → type personnalisé.
Chaque méthode lève PendingException et cite les exigences et l'origine (fichier:ligne).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from gherkin.pickles.compiler import Compiler

from neospec.config import RE_ID_SEUL
from neospec.validation.gherkin import analyser

MOTS_CLES = {"Context": "Soit", "Action": "Quand", "Outcome": "Alors", "Unknown": "Soit"}
TYPES_JAVA = {"string": "String", "int": "int", "decimal": "BigDecimal"}
REGEX_DECIMAL = r"\d+(?:,\d+)?"


@dataclass(frozen=True)
class TypePerso:
    nom: str
    alternatives: tuple[str, ...]

    def regex_java(self) -> str:
        return "|".join(re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", a) for a in sorted(self.alternatives, key=len, reverse=True))


@dataclass
class Etape:
    mot_cle: str
    texte: str
    argument: str | None
    exigences: set[str]
    origine: str


@dataclass
class Definition:
    mot_cle: str
    expression: str
    slots: list[str]
    argument: str | None
    exigences: set[str] = field(default_factory=set)
    origines: list[str] = field(default_factory=list)
    exemple: str = ""


def charger_types(chemin: Path | None) -> list[TypePerso]:
    """YAML : `types: {sousType: [CP, RTT, SANS_SOLDE], debut: ["au matin", "l'après-midi"]}`."""
    if not chemin:
        return []
    donnees = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    return [TypePerso(nom, tuple(str(a) for a in alts)) for nom, alts in (donnees.get("types") or {}).items()]


def collecter_etapes(fichiers: list[Path]) -> list[Etape]:
    """Étapes concrètes (pickles : plans du scénario développés, conjonctions résolues)."""
    etapes: list[Etape] = []
    for fichier in fichiers:
        doc = analyser(fichier.read_text(encoding="utf-8"))
        lignes: dict[str, int] = {}

        def indexer(noeud: Any) -> None:
            if isinstance(noeud, dict):
                if "id" in noeud and "location" in noeud:
                    lignes[noeud["id"]] = noeud["location"]["line"]
                for v in noeud.values():
                    indexer(v)
            elif isinstance(noeud, list):
                for v in noeud:
                    indexer(v)

        indexer(doc)
        doc["uri"] = fichier.name
        for pickle in Compiler().compile(doc):
            ids = {t["name"][1:] for t in pickle["tags"] if RE_ID_SEUL.match(t["name"][1:])}
            for st in pickle["steps"]:
                arg = st.get("argument") or {}
                etapes.append(Etape(
                    mot_cle=MOTS_CLES.get(st.get("type", "Unknown"), "Soit"),
                    texte=st["text"],
                    argument="table" if "dataTable" in arg else "docstring" if "docString" in arg else None,
                    exigences=ids,
                    origine=f"{fichier.name}:{lignes.get(st['astNodeIds'][0], '?')}",
                ))
    return etapes


def _echapper(litteral: str) -> str:
    """Caractères spéciaux des expressions Cucumber : ( ) { } / \\ ."""
    return re.sub(r"([(){}/\\])", r"\\\1", litteral)


def expression_cucumber(texte: str, types: list[TypePerso] | tuple[TypePerso, ...] = ()) -> tuple[str, list[str]]:
    """Transforme le texte concret d'une étape en expression Cucumber et liste de paramètres.

    Ordre de reconnaissance, de gauche à droite :
    1. texte entre guillemets doubles → {string} ;
    2. alternative d'un type personnalisé (la plus longue d'abord, mot entier) → {nom} ;
    3. nombre décimal à virgule (1,5) → {decimal} ; entier → {int} (mot entier) ;
    4. le reste est littéral, avec ( ) { } / et \\ échappés.
    Exemple : '"alice" a 20 jours en 2027' → ('{string} a {int} jours en {int}', ['string', 'int', 'int']).
    """
    # TODO TP2 : une expression régulière à alternatives (guillemets, alternatives des types, décimal, entier), re.finditer, littéraux passés à _echapper, liste des slots dans l'ordre.
    raise NotImplementedError("TODO TP2 : expression_cucumber")


def unifier(etapes: list[Etape], types: list[TypePerso]) -> list[Definition]:
    """Regroupe les étapes de même forme ; un nombre décimal quelque part rend le paramètre {decimal}."""
    groupes: dict[str, Definition] = {}
    for e in etapes:
        expr, slots = expression_cucumber(e.texte, types)
        cle = re.sub(r"\{(?:int|decimal)\}", "{num}", expr)
        d = groupes.get(cle)
        if d is None:
            d = groupes[cle] = Definition(e.mot_cle, expr, slots, e.argument, exemple=e.texte)
        else:
            d.slots = ["decimal" if "decimal" in (a, b) else a for a, b in zip(d.slots, slots)]
        d.exigences |= e.exigences
        if e.origine not in d.origines:
            d.origines.append(e.origine)
    for cle, d in groupes.items():
        nums = iter(s for s in d.slots if s in ("int", "decimal"))
        d.expression = re.sub(r"\{num\}", lambda _m: "{" + next(nums) + "}", cle)
    return list(groupes.values())


def nom_methode(mot_cle: str, expression: str, deja: set[str]) -> str:
    texte = re.sub(r"\{[^}]*\}", " ", expression.replace("\\", ""))
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    mots = [m for m in re.split(r"[^A-Za-z0-9]+", texte) if m][:10]
    base = mot_cle.lower() + "".join(m[:1].upper() + m[1:] for m in mots)
    base = base[:70] or mot_cle.lower()
    nom, n = base, 2
    while nom in deja:
        nom, n = f"{base}{n}", n + 1
    deja.add(nom)
    return nom


def _chaine_java(texte: str) -> str:
    return '"' + texte.replace("\\", "\\\\").replace('"', '\\"') + '"'


def generer_classe(definitions: list[Definition], paquet: str, classe: str, types: list[TypePerso], source: str) -> str:
    utilises = {s for d in definitions for s in d.slots}
    persos = [t for t in types if t.nom in utilises]
    imports = []
    if any(d.argument == "table" for d in definitions):
        imports.append("io.cucumber.datatable.DataTable")
    if persos or "decimal" in utilises:
        imports.append("io.cucumber.java.ParameterType")
    imports.append("io.cucumber.java.PendingException")
    imports += [f"io.cucumber.java.fr.{m}" for m in sorted({d.mot_cle for d in definitions})]
    if "decimal" in utilises:
        imports.append("java.math.BigDecimal")
    lignes = [f"package {paquet};", ""] + [f"import {i};" for i in imports] + [
        "",
        "/**",
        f" * Squelettes générés par neospec à partir de {source} ({len(definitions)} formulations d'étapes).",
        " * Chaque méthode lève PendingException : à implémenter au J7 (API : MockMvc ou RestAssured ; UI : Playwright).",
        " * Une expression modifiée ici doit l'être aussi dans les scénarios et dans ETAPES.md.",
        " */",
        f"public class {classe} {{",
    ]
    if "decimal" in utilises:
        lignes += ["", f"    @ParameterType({_chaine_java(REGEX_DECIMAL)})",
                   "    public BigDecimal decimal(String valeur) {",
                   "        return new BigDecimal(valeur.replace(',', '.'));", "    }"]
    for t in persos:
        lignes += ["", f"    @ParameterType({_chaine_java(t.regex_java())})",
                   f"    public String {t.nom}(String valeur) {{", "        return valeur;", "    }"]
    deja: set[str] = {t.nom for t in persos} | {"decimal"}
    for d in definitions:
        params = [f"{TYPES_JAVA.get(s, 'String')} arg{i}" for i, s in enumerate(d.slots, start=1)]
        if d.argument == "table":
            params.append("DataTable table")
        elif d.argument == "docstring":
            params.append("String docString")
        triees = sorted(d.exigences, key=lambda i: (not i.startswith("EF"), i))
        exig = (", ".join(triees[:6]) + (f" +{len(triees) - 6}" if len(triees) > 6 else "")) or "sans exigence"
        origines = ", ".join(d.origines[:3]) + (f" (+{len(d.origines) - 3})" if len(d.origines) > 3 else "")
        lignes += [
            "",
            f"    // [{exig}] {origines}",
            f"    // exemple : {d.exemple}",
            f"    @{d.mot_cle}({_chaine_java(d.expression)})",
            f"    public void {nom_methode(d.mot_cle, d.expression, deja)}({', '.join(params)}) {{",
            f"        throw new PendingException({_chaine_java('TODO : ' + d.expression)});",
            "    }",
        ]
    lignes += ["}", ""]
    return "\n".join(lignes)


def generer_runner(paquet: str, classe: str, ressource: str, tags: str) -> str:
    return f"""package {paquet};

import static io.cucumber.junit.platform.engine.Constants.FILTER_TAGS_PROPERTY_NAME;
import static io.cucumber.junit.platform.engine.Constants.GLUE_PROPERTY_NAME;
import static io.cucumber.junit.platform.engine.Constants.PLUGIN_PROPERTY_NAME;

import org.junit.platform.suite.api.ConfigurationParameter;
import org.junit.platform.suite.api.IncludeEngines;
import org.junit.platform.suite.api.SelectClasspathResource;
import org.junit.platform.suite.api.Suite;

/** Lanceur JUnit Platform des scénarios de {ressource} (généré par neospec). */
@Suite
@IncludeEngines("cucumber")
@SelectClasspathResource("{ressource}")
@ConfigurationParameter(key = GLUE_PROPERTY_NAME, value = "{paquet}")
@ConfigurationParameter(key = FILTER_TAGS_PROPERTY_NAME, value = "{tags}")
@ConfigurationParameter(key = PLUGIN_PROPERTY_NAME, value = "pretty")
public class {classe} {{
}}
"""


def nom_classe(type_: str) -> str:
    return "".join(m.capitalize() for m in type_.lower().split("_"))
