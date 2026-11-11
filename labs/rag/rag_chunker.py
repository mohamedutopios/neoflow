"""Découpage du corpus NeoFlow en chunks citables.

- Java, TypeScript/TSX, JavaScript : AST Tree-sitter -> un chunk par type (petit)
  ou un résumé de type + un chunk par méthode/fonction (gros), Javadoc/JSDoc incluse.
- Markdown : un chunk par section (chemin de titres), blocs de code respectés.
- YAML : un chunk par clé de premier niveau ; SQL : par instruction ; autres : fenêtres de lignes.

Chaque chunk garde des numéros de ligne exacts (1-based, inclusifs) pour la citation
chemin:début-fin@commit. Les résumés de type (kind = class_summary) sont synthétiques :
leur plage de lignes couvre tout le type.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

LANG_BY_EXT = {
    ".java": "java", ".ts": "typescript", ".mts": "typescript", ".cts": "typescript", ".tsx": "tsx",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".md": "markdown", ".markdown": "markdown", ".yml": "yaml", ".yaml": "yaml", ".sql": "sql",
    ".xml": "xml", ".json": "json", ".properties": "properties", ".sh": "shell", ".css": "css",
    ".html": "html", ".txt": "text", ".adoc": "asciidoc", ".toml": "toml",
}
AST_LANGS = {"java", "typescript", "tsx", "javascript"}


@dataclass
class Chunk:
    path: str
    start_line: int
    end_line: int
    text: str
    symbol: str
    kind: str
    language: str
    extra: dict = field(default_factory=dict)


def language_of(rel_path: str) -> str:
    name = Path(rel_path).name
    if name == "Dockerfile":
        return "dockerfile"
    return LANG_BY_EXT.get(Path(rel_path).suffix.lower(), "text")


# --------------------------------------------------------------------------- #
# Parseurs Tree-sitter : wheels dédiées (embarquées) puis tree-sitter-language-pack
# --------------------------------------------------------------------------- #

_PARSERS: dict[str, object] = {}
PARSER_BACKEND: dict[str, str] = {}


def get_parser(lang: str, backend: str = "auto"):
    """Parseur Tree-sitter pour java / typescript / tsx / javascript, ou None.

    backend 'auto' : wheels tree_sitter_java / tree_sitter_typescript / tree_sitter_javascript
    (grammaires embarquées dans le paquet, aucun téléchargement), sinon
    tree-sitter-language-pack (télécharge la grammaire au premier usage, puis cache local).
    """
    if lang in _PARSERS:
        return _PARSERS[lang]
    parser = None
    if backend in ("auto", "wheels"):
        try:
            from tree_sitter import Language, Parser

            if lang == "java":
                import tree_sitter_java as mod
                parser = Parser(Language(mod.language()))
            elif lang in ("typescript", "tsx"):
                import tree_sitter_typescript as mod
                parser = Parser(Language(mod.language_tsx() if lang == "tsx" else mod.language_typescript()))
            elif lang == "javascript":
                import tree_sitter_javascript as mod
                parser = Parser(Language(mod.language()))
            if parser is not None:
                PARSER_BACKEND[lang] = "wheel"
        except Exception:
            parser = None
    if parser is None and backend in ("auto", "language-pack"):
        try:
            from tree_sitter_language_pack import get_parser as pack_parser

            parser = pack_parser(lang)
            PARSER_BACKEND[lang] = "language-pack"
        except Exception:
            parser = None
    _PARSERS[lang] = parser
    return parser


# --------------------------------------------------------------------------- #
# Code : parcours de l'AST
# --------------------------------------------------------------------------- #

JAVA_TYPES = {
    "class_declaration": "class", "interface_declaration": "interface", "enum_declaration": "enum",
    "record_declaration": "record", "annotation_type_declaration": "annotation",
}
JAVA_FUNCS = {"method_declaration": "method", "constructor_declaration": "constructor",
              "compact_constructor_declaration": "constructor"}
TS_TYPES = {
    "class_declaration": "class", "abstract_class_declaration": "class", "class": "class",
    "interface_declaration": "interface", "enum_declaration": "enum", "type_alias_declaration": "type",
}
TS_FUNCS = {"function_declaration": "function", "generator_function_declaration": "function",
            "method_definition": "method"}
FUNC_VALUES = {"arrow_function", "function_expression", "function", "generator_function"}
TEST_CALLS = {"test", "it", "describe"}
COMMENT_TYPES = {"comment", "line_comment", "block_comment"}


class _CodeChunker:
    def __init__(self, rel_path: str, source: bytes, lang: str, opts: dict):
        self.rel_path = rel_path
        self.source = source
        self.lines = source.decode("utf-8", errors="replace").split("\n")
        self.lang = lang
        self.max_lines = int(opts.get("max_lines", 80))
        self.overlap = int(opts.get("overlap_lines", 5))
        self.small_type = int(opts.get("small_type_lines", 60))
        self.class_summary = bool(opts.get("class_summary", True))
        self.min_lines = int(opts.get("min_lines", 4))
        self.chunks: list[Chunk] = []
        self.covered: set[int] = set()
        self.is_java = lang == "java"
        self.types = JAVA_TYPES if self.is_java else TS_TYPES
        self.funcs = JAVA_FUNCS if self.is_java else TS_FUNCS

    # -- utilitaires ------------------------------------------------------- #
    def text_of(self, node) -> str:
        return self.source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def name_of(self, node) -> str:
        name = node.child_by_field_name("name")
        return self.text_of(name) if name is not None else "anonyme"

    def span_start(self, node) -> int:
        """Ligne de début (0-based) en incluant la Javadoc/JSDoc et les commentaires adjacents."""
        start = node.start_point[0]
        prev = node.prev_named_sibling
        while prev is not None and prev.type in COMMENT_TYPES and prev.end_point[0] >= start - 1:
            start = prev.start_point[0]
            prev = prev.prev_named_sibling
        return start

    def emit(self, start0: int, end0: int, symbol: str, kind: str, text: str | None = None, **extra):
        """Émet un chunk (lignes 0-based inclusives) ; découpe en fenêtres s'il est trop long."""
        total = end0 - start0 + 1
        if text is None and total > self.max_lines:
            step = max(1, self.max_lines - self.overlap)
            windows, s = [], start0
            while True:
                e = min(end0, s + self.max_lines - 1)
                windows.append((s, e))
                if e >= end0:
                    break
                s += step
            for idx, (s, e) in enumerate(windows, 1):
                self._append(s, e, symbol, kind, None, part=f"{idx}/{len(windows)}", **extra)
            return
        self._append(start0, end0, symbol, kind, text, **extra)

    def _append(self, s: int, e: int, symbol: str, kind: str, text: str | None, **extra):
        body = text if text is not None else "\n".join(self.lines[s:e + 1])
        if not body.strip():
            return
        self.chunks.append(Chunk(self.rel_path, s + 1, e + 1, body, symbol, kind, self.lang, dict(extra)))
        if text is None or kind != "class_summary":
            self.covered.update(range(s, e + 1))

    # -- classification des nœuds ------------------------------------------ #
    def func_value(self, declarator):
        value = declarator.child_by_field_name("value")
        if value is not None and value.type in ("call_expression",):  # memo(() => ...), forwardRef(...)
            args = value.child_by_field_name("arguments")
            if args is not None:
                for arg in args.named_children:
                    if arg.type in FUNC_VALUES:
                        return arg
        return value if value is not None and value.type in FUNC_VALUES else None

    def iife_body(self, declarator):
        """var NeoUtils = (function () { ... })();  -> corps de la fonction (portée module)."""
        value = declarator.child_by_field_name("value")
        if value is None or value.type != "call_expression":
            return None
        fn = value.child_by_field_name("function")
        while fn is not None and fn.type == "parenthesized_expression":
            fn = fn.named_children[0] if fn.named_children else None
        if fn is not None and fn.type in FUNC_VALUES:
            return fn.child_by_field_name("body")
        return None

    def test_call(self, node):
        """test('libellé', async () => {...}) / describe(...) -> (kind, libellé, callback)."""
        if node.type != "expression_statement" or not node.named_children:
            return None
        call = node.named_children[0]
        if call.type != "call_expression":
            return None
        callee = call.child_by_field_name("function")
        if callee is None:
            return None
        callee_text = self.text_of(callee)
        base = callee_text.split(".")[0]
        if base not in TEST_CALLS:
            return None
        is_suite = base == "describe" or ".describe" in callee_text
        args = call.child_by_field_name("arguments")
        label, callback = None, None
        for arg in (args.named_children if args is not None else []):
            if label is None and arg.type in ("string", "template_string"):
                label = self.text_of(arg).strip("'\"`")
            if arg.type in FUNC_VALUES:
                callback = arg
        if label is None:
            return None
        return ("test_suite" if is_suite else "test"), f"{callee_text}: {label}", callback

    # -- parcours ---------------------------------------------------------- #
    def walk(self, node, scope: list[str], span_node=None):
        for child in node.named_children:
            self.visit(child, scope, span_node=None)

    def visit(self, node, scope: list[str], span_node=None):
        t = node.type
        span = span_node or node
        if t == "export_statement":
            decl = node.child_by_field_name("declaration")
            targets = [decl] if decl is not None else [c for c in node.named_children if c.type not in COMMENT_TYPES]
            for target in targets:
                self.visit(target, scope, span_node=node)
            return
        if t in self.types:
            self.visit_type(node, span, scope)
            return
        if t in self.funcs:
            self.visit_func(node, span, scope, self.funcs[t])
            return
        if t in ("lexical_declaration", "variable_declaration"):
            for declarator in node.named_children:
                if declarator.type != "variable_declarator":
                    continue
                name = self.name_of(declarator)
                fn = self.func_value(declarator)
                if fn is not None:
                    self.visit_func(declarator, span, scope, "function", name=name)
                    continue
                body = self.iife_body(declarator)
                if body is not None:
                    self.walk(body, scope + [name])
            return
        if t in ("public_field_definition", "field_definition"):
            value = node.child_by_field_name("value")
            if value is not None and value.type in FUNC_VALUES:
                self.visit_func(node, span, scope, "method")
            return
        test = self.test_call(node) if t == "expression_statement" else None
        if test is not None:
            kind, label, callback = test
            start, end = self.span_start(span), span.end_point[0]
            if kind == "test_suite" and callback is not None and end - start + 1 > self.small_type:
                body = callback.child_by_field_name("body")
                if body is not None:
                    self.walk(body, scope + [label])
                    return
            self.emit(start, end, ".".join(scope + [label]), kind)
            return
        if t in ("program", "statement_block", "class_body", "interface_body", "enum_body",
                 "enum_body_declarations", "ambient_declaration", "module", "internal_module"):
            self.walk(node, scope)

    def member_names(self, body) -> str:
        """Noms des membres (méthodes, champs, constantes) : métadonnée « members » du chunk."""
        names: list[str] = []
        children = list(body.named_children) if body is not None else []
        for member in children:
            if member.type == "enum_body_declarations":
                children.extend(member.named_children)
                continue
            target = member
            if member.type in ("field_declaration", "lexical_declaration"):
                target = member.child_by_field_name("declarator") or next(
                    (c for c in member.named_children if c.type == "variable_declarator"), None)
            name = target.child_by_field_name("name") if target is not None else None
            if name is not None:
                text = self.text_of(name)
                if text not in names:
                    names.append(text)
        return ", ".join(names[:40])

    def visit_type(self, node, span, scope):
        name = self.name_of(node)
        qual = scope + [name]
        start, end = self.span_start(span), span.end_point[0]
        kind = self.types[node.type]
        body = node.child_by_field_name("body")
        members = self.member_names(body)
        if end - start + 1 <= self.small_type:
            self.emit(start, end, ".".join(qual), kind, members=members)
            return
        if self.class_summary:
            self.emit(start, end, ".".join(qual), "class_summary", text=self.skeleton(span, body), members=members)
            # en-tête et champs sont portés par le résumé : pas de chunk « module » en double
            header_end = body.start_point[0] if body is not None else end
            self.covered.update(range(start, header_end + 1))
            for member in (body.named_children if body is not None else []):
                if member.type not in self.funcs and member.type not in self.types:
                    self.covered.update(range(member.start_point[0], member.end_point[0] + 1))
        if body is not None:
            self.walk(body, qual)

    def visit_func(self, node, span, scope, kind, name: str | None = None):
        name = name or self.name_of(node)
        start, end = self.span_start(span), span.end_point[0]
        self.emit(start, end, ".".join(scope + [name]), kind)

    def skeleton(self, span, body) -> str:
        """Résumé d'un gros type : en-tête, champs, signatures (corps remplacés par { … })."""
        if body is None:
            return self.text_of(span)
        header = self.source[span.start_byte:body.start_byte].decode("utf-8", errors="replace").rstrip()
        out = [header + " {"]
        for member in body.named_children:
            if member.type in COMMENT_TYPES:
                continue
            mbody = member.child_by_field_name("body")
            if member.type in self.funcs and mbody is not None:
                sig = self.source[member.start_byte:mbody.start_byte].decode("utf-8", errors="replace").strip()
                out.append("    " + " ".join(sig.split()) + " { … }")
            elif member.type in self.types:
                out.append(f"    {self.types[member.type]} {self.name_of(member)} {{ … }}")
            else:
                text = " ".join(self.text_of(member).split())
                out.append("    " + (text if len(text) <= 160 else text[:157] + "…"))
        out.append("}")
        return "\n".join(out)

    def leftovers(self):
        """Lignes significatives non couvertes (constantes, config, appels de haut niveau)."""
        trivial = re.compile(r"^\s*(import\b|package\b|export \{|\}|\)|;|//|/\*|\*|$)")
        run: list[int] = []
        groups: list[list[int]] = []
        for i, line in enumerate(self.lines):
            if i in self.covered:
                if run:
                    groups.append(run)
                    run = []
                continue
            run.append(i)
        if run:
            groups.append(run)
        for group in groups:
            meaningful = [i for i in group if not trivial.match(self.lines[i])]
            if len(meaningful) >= 2:
                self.emit(meaningful[0], meaningful[-1], Path(self.rel_path).name, "module")

    def merge_small(self):
        """Regroupe les membres minuscules et adjacents d'un même type (accesseurs, alias de type)
        en un chunk « group » : une ligne isolée est un mauvais passage pour la recherche."""
        def parent(c: Chunk) -> str:
            return c.symbol.rsplit(".", 1)[0] if "." in c.symbol else ""

        out: list[Chunk] = []
        group: list[Chunk] = []

        def flush():
            if len(group) >= 2:
                s, e = group[0].start_line, group[-1].end_line
                names = [g.symbol.rsplit(".", 1)[-1] for g in group]
                prefix = parent(group[0])
                symbol = (prefix + "." if prefix else "") + f"{names[0]} … {names[-1]}"
                out.append(Chunk(self.rel_path, s, e, "\n".join(self.lines[s - 1:e]), symbol, "group",
                                 self.lang, {"members": ", ".join(names)}))
            else:
                out.extend(group)
            group.clear()

        for c in sorted(self.chunks, key=lambda c: (c.start_line, c.kind != "class_summary")):
            small = c.kind not in ("class_summary", "test", "test_suite") and c.end_line - c.start_line + 1 <= self.min_lines
            if small and group and parent(c) == parent(group[-1]) and c.start_line - group[-1].end_line <= 2 \
                    and c.end_line - group[0].start_line < self.max_lines:
                group.append(c)
                continue
            flush()
            (group if small else out).append(c)
        flush()
        self.chunks = out

    def run(self, tree) -> list[Chunk]:
        self.visit(tree.root_node, [])
        self.leftovers()
        if self.min_lines > 0:
            self.merge_small()
        self.chunks.sort(key=lambda c: (c.start_line, c.kind != "class_summary"))
        return self.chunks


def chunk_code_ast(rel_path: str, text: str, lang: str, opts: dict) -> list[Chunk] | None:
    parser = get_parser(lang, opts.get("parser_backend", "auto"))
    if parser is None:
        return None
    source = text.encode("utf-8")
    tree = parser.parse(source)
    chunks = _CodeChunker(rel_path, source, lang, opts).run(tree)
    if tree.root_node.has_error:
        for chunk in chunks:
            chunk.extra["parse_error"] = True
    return chunks


# --------------------------------------------------------------------------- #
# Markdown : sections par titres
# --------------------------------------------------------------------------- #


def parse_front_matter(lines: list[str]) -> tuple[dict, int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    for i in range(1, min(len(lines), 60)):
        if lines[i].strip() == "---":
            try:
                data = yaml.safe_load("\n".join(lines[1:i])) or {}
            except yaml.YAMLError:
                data = {}
            return (data if isinstance(data, dict) else {}), i + 1
    return {}, 0


def chunk_markdown(rel_path: str, text: str, opts: dict) -> list[Chunk]:
    lines = text.split("\n")
    meta, first = parse_front_matter(lines)
    status = str(meta.get("statut") or meta.get("status") or "").strip().lower() or None
    max_lines = int(opts.get("max_lines", 60))
    sections: list[tuple[int, int, list[str]]] = []
    stack: list[tuple[int, str]] = []
    in_fence = False
    cur_start, cur_path = first, []
    title = None
    for idx in range(first, len(lines)):
        line = lines[idx]
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        m = None if in_fence else re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if m:
            if idx > cur_start:
                sections.append((cur_start, idx - 1, cur_path))
            level, heading = len(m.group(1)), m.group(2).strip()
            title = title or (heading if level == 1 else None)
            stack = [s for s in stack if s[0] < level] + [(level, heading)]
            cur_start, cur_path = idx, [h for _, h in stack]
    sections.append((cur_start, len(lines) - 1, cur_path))
    title = title or Path(rel_path).stem
    chunks: list[Chunk] = []
    pending_heading: tuple[int, list[str]] | None = None
    for start, end, path in sections:
        body = [l for l in lines[start:end + 1] if l.strip()]
        if not body:
            continue
        if len(body) == 1 and body[0].lstrip().startswith("#"):
            pending_heading = pending_heading or (start, path)  # titre sans corps : fusion avec la suite
            continue
        if pending_heading is not None:
            start = pending_heading[0]
            pending_heading = None
        symbol = " > ".join(path) if path else title
        for s, e in _paragraph_windows(lines, start, end, max_lines):
            chunk_text = "\n".join(lines[s:e + 1]).strip("\n")
            if chunk_text.strip():
                chunks.append(Chunk(rel_path, s + 1, e + 1, chunk_text, symbol, "section", "markdown",
                                    {"doc_title": title, "status": status}))
    return chunks


def _paragraph_windows(lines: list[str], start: int, end: int, max_lines: int):
    """Découpe une section trop longue sur des lignes vides, hors bloc de code."""
    if end - start + 1 <= max_lines:
        yield start, end
        return
    s = start
    while s <= end:
        e = min(end, s + max_lines - 1)
        if e < end:
            in_fence = False
            cut = None
            for i in range(s, e + 1):
                if lines[i].lstrip().startswith(("```", "~~~")):
                    in_fence = not in_fence
                if not in_fence and not lines[i].strip() and i > s + max_lines // 2:
                    cut = i
            e = cut or e
        yield s, e
        s = e + 1


# --------------------------------------------------------------------------- #
# YAML, SQL, autres fichiers
# --------------------------------------------------------------------------- #


def small_file_chunk(rel_path: str, text: str, lang: str, kind: str, symbol: str) -> list[Chunk]:
    """Fichier court : un seul chunk, pour ne pas séparer un commentaire d'en-tête de son contenu."""
    lines = text.rstrip("\n").split("\n")
    return [Chunk(rel_path, 1, len(lines), "\n".join(lines), symbol, kind, lang)] if text.strip() else []


def chunk_yaml(rel_path: str, text: str, opts: dict) -> list[Chunk]:
    """Un chunk par clé de premier niveau ; documents multiples (---) et profils Spring repérés.
    Fichier de max_lines lignes ou moins : un seul chunk (symbole = clés de premier niveau)."""
    lines = text.split("\n")
    max_lines = int(opts.get("max_lines", 40))
    if len(text.rstrip("\n").split("\n")) <= max_lines:
        keys = [m.group(1) for m in (re.match(r"^([A-Za-z0-9_.\-]+):", l) for l in lines) if m]
        return small_file_chunk(rel_path, text, "yaml", "config", ", ".join(dict.fromkeys(keys)) or Path(rel_path).name)
    docs: list[tuple[int, int]] = []
    doc_start = 0
    for i, line in enumerate(lines):
        if line.startswith("---"):
            if i > doc_start:
                docs.append((doc_start, i - 1))
            doc_start = i + 1
    docs.append((doc_start, len(lines) - 1))
    blocks: list[list] = []  # [start, end, key, profil]
    for d_start, d_end in docs:
        doc_text = "\n".join(lines[d_start:d_end + 1])
        prof = re.search(r"on-profile:\s*['\"]?([\w,-]+)", doc_text)
        profile = prof.group(1) if prof else None
        first_block = len(blocks)
        for i in range(d_start, d_end + 1):
            m = re.match(r"^([A-Za-z0-9_.\-\"']+):", lines[i])
            if m:
                if len(blocks) > first_block:
                    blocks[-1][1] = i - 1
                blocks.append([i, d_end, m.group(1).strip("\"'"), profile])
        # commentaires qui précèdent une clé : rattachés à cette clé
        for idx in range(first_block + 1, len(blocks)):
            s = blocks[idx][0]
            while s - 1 > blocks[idx - 1][0] and lines[s - 1].lstrip().startswith("#"):
                s -= 1
            if s != blocks[idx][0]:
                blocks[idx - 1][1] = s - 1
                blocks[idx][0] = s
        if len(blocks) > first_block and blocks[first_block][0] > d_start:
            head = [l for l in lines[d_start:blocks[first_block][0]] if l.strip()]
            if head and all(l.lstrip().startswith("#") for l in head):
                blocks[first_block][0] = d_start
    if not blocks:
        return chunk_lines(rel_path, text, "yaml", opts)
    chunks: list[Chunk] = []
    for start, end, key, prof in blocks:
        while end > start and not lines[end].strip():
            end -= 1
        symbol = f"{key} [profil {prof}]" if prof else key
        if end - start + 1 <= max_lines:
            chunks.append(Chunk(rel_path, start + 1, end + 1, "\n".join(lines[start:end + 1]), symbol, "config", "yaml"))
        else:
            for c in chunk_lines(rel_path, "\n".join(lines[start:end + 1]), "yaml", opts, offset=start):
                c.symbol, c.kind = symbol, "config"
                chunks.append(c)
    return chunks


_SQL_STMT = re.compile(r"^\s*(CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX|SEQUENCE|VIEW)|INSERT\s+INTO|ALTER\s+TABLE)\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"]+)", re.IGNORECASE)


def chunk_sql(rel_path: str, text: str, opts: dict) -> list[Chunk]:
    lines = text.split("\n")
    max_lines = int(opts.get("max_lines", 40))
    starts: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = _SQL_STMT.match(line)
        if m:
            verb = " ".join(m.group(1).upper().split()).replace("UNIQUE ", "")
            s = i
            while s - 1 >= 0 and lines[s - 1].lstrip().startswith("--"):
                s -= 1
            starts.append((s, f"{verb} {m.group(2).strip(chr(34))}"))
    if not starts:
        return chunk_lines(rel_path, text, "sql", opts)
    merged: list[list] = []
    for idx, (s, sym) in enumerate(starts):
        e = (starts[idx + 1][0] - 1) if idx + 1 < len(starts) else len(lines) - 1
        if merged and merged[-1][2] == sym and e - merged[-1][0] < max_lines:
            merged[-1][1] = e  # INSERT consécutifs dans la même table
        else:
            merged.append([s, e, sym])
    if starts[0][0] > 0 and any(l.strip() for l in lines[:starts[0][0]]):
        merged.insert(0, [0, starts[0][0] - 1, Path(rel_path).name])
    chunks = []
    for s, e, sym in merged:
        while e > s and not lines[e].strip():
            e -= 1
        for c in chunk_lines(rel_path, "\n".join(lines[s:e + 1]), "sql", opts, offset=s):
            c.symbol, c.kind = sym, "sql"
            chunks.append(c)
    return chunks


def chunk_lines(rel_path: str, text: str, lang: str, opts: dict, offset: int = 0) -> list[Chunk]:
    lines = text.split("\n")
    max_lines = int(opts.get("max_lines", 40))
    overlap = int(opts.get("overlap_lines", 5))
    chunks: list[Chunk] = []
    s = 0
    while s < len(lines):
        e = min(len(lines) - 1, s + max_lines - 1)
        body = "\n".join(lines[s:e + 1])
        if body.strip():
            chunks.append(Chunk(rel_path, offset + s + 1, offset + e + 1, body, Path(rel_path).name, "lines", lang))
        if e >= len(lines) - 1:
            break
        s = e + 1 - overlap
    return chunks


# --------------------------------------------------------------------------- #
# Point d'entrée
# --------------------------------------------------------------------------- #


def from_component(rel_path: str, text: str, lang: str, raw: list) -> list[Chunk]:
    """Convertit et contrôle la sortie d'un chunker de TP (liste de dicts)."""
    n_lines = len(text.split("\n"))
    chunks: list[Chunk] = []
    for i, d in enumerate(raw):
        try:
            s, e = int(d["start_line"]), int(d["end_line"])
            body = d.get("text") or "\n".join(text.split("\n")[s - 1:e])
            chunk = Chunk(rel_path, s, e, body, str(d.get("symbol") or ""), str(d.get("kind") or "lines"), lang,
                          {k: d[k] for k in ("members", "part") if d.get(k)})
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"chunker de TP, {rel_path}, élément {i} : {exc!r} (attendu : start_line, end_line, symbol, kind)") from exc
        if not (1 <= s <= e <= n_lines) or not body.strip():
            raise ValueError(f"chunker de TP, {rel_path}, élément {i} : lignes {s}-{e} hors du fichier (1-{n_lines}) ou texte vide")
        chunks.append(chunk)
    return chunks


def chunk_file(rel_path: str, text: str, chunking_cfg: dict, custom_code_chunker=None) -> list[Chunk]:
    """Découpe un fichier. `custom_code_chunker` : composant de TP (composants.chunker_code)
    appelé pour le code ; s'il renvoie None, le chunker du lab prend le relais."""
    lang = language_of(rel_path)
    code_opts = chunking_cfg.get("code", {})
    if lang == "markdown":
        return chunk_markdown(rel_path, text, chunking_cfg.get("docs", {}))
    if lang in AST_LANGS and custom_code_chunker is not None and code_opts.get("strategy", "ast") == "ast":
        raw = custom_code_chunker(rel_path, text, lang, code_opts)
        if raw is not None:
            return from_component(rel_path, text, lang, raw)
    if lang in AST_LANGS and code_opts.get("strategy", "ast") == "ast":
        chunks = chunk_code_ast(rel_path, text, lang, code_opts)
        if chunks:
            return chunks
    if lang in AST_LANGS:
        return chunk_lines(rel_path, text, lang, code_opts)
    config_opts = chunking_cfg.get("config", {})
    if lang == "yaml":
        return chunk_yaml(rel_path, text, config_opts)
    if lang == "sql":
        return chunk_sql(rel_path, text, config_opts)
    return chunk_lines(rel_path, text, lang, config_opts)
