"""
Mutation operator plugin API and the engine that applies operators.

Writing an operator:

    from mutators.core import MutationOperator, Edit

    class MyOperator(MutationOperator):
        name = "MYOP"                       # unique, used on the CLI
        description = "what it mutates"
        node_types = ("binary_expression",) # tree-sitter node types to visit

        def mutate(self, node, src):
            yield Edit("label", node.start_byte, node.end_byte, "replacement")

Defining the subclass registers it. Drop the file in mutators/operators/
to make it built in, or load it with `mutate.py --plugin path/to/file.py`.
"""

import importlib
import importlib.util
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import tree_sitter_c
from tree_sitter import Language, Node, Parser, Tree

C = Language(tree_sitter_c.language())


@dataclass(frozen=True)
class Edit:
    """One textual change: replace src[start:end] with `replacement`."""
    label: str
    start: int
    end: int
    replacement: str


@dataclass
class Mutant:
    mid: int
    operator: str
    label: str
    line: int
    start: int
    end: int
    replacement: str
    before: str = ""
    after: str = ""
    status: str = "pending"
    failed_tests: list = field(default_factory=list)

    def apply(self, src: bytes) -> bytes:
        return src[:self.start] + self.replacement.encode() + src[self.end:]


class MutationOperator:
    """Base class. Subclasses with a `name` register themselves."""

    name: str = ""
    description: str = ""
    node_types: tuple = ()
    enabled_by_default: bool = True

    registry: dict = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.name:
            return  # abstract helper class
        if cls.name in MutationOperator.registry:
            raise ValueError(f"duplicate mutation operator name {cls.name!r}")
        MutationOperator.registry[cls.name] = cls

    def prepare(self, tree: Tree, src: bytes) -> None:
        """Optional hook, called once per file before any mutate() call."""

    def mutate(self, node: Node, src: bytes) -> Iterable[Edit]:
        raise NotImplementedError


# ---------------------------------------------------------------- helpers

def text(node: Node) -> str:
    return node.text.decode()


def field_text(node: Node, name: str) -> str:
    return text(node.child_by_field_name(name))


def replace_operator(node: Node, repl: str, label: str = None) -> Edit:
    """Swap the operator token of a binary/unary expression."""
    op = node.child_by_field_name("operator")
    return Edit(label or f"{text(op)} -> {repl}", op.start_byte, op.end_byte,
                repl)


def replace_node(node: Node, repl: str, label: str) -> Edit:
    return Edit(label, node.start_byte, node.end_byte, repl)


# ---------------------------------------------------------------- loading

def load_builtin_operators() -> None:
    """Import every module in mutators/operators so their classes register."""
    from . import operators
    for mod in pkgutil.iter_modules(operators.__path__):
        importlib.import_module(f"{operators.__name__}.{mod.name}")


def load_plugin(path: str) -> None:
    """Import an operator module from an arbitrary file path."""
    p = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(f"mutator_plugin_{p.stem}", p)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plugin {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


def select_operators(only=None, exclude=None) -> list:
    """Instantiate the chosen operators, in registration order."""
    reg = MutationOperator.registry
    unknown = [n for n in (only or []) + (exclude or []) if n not in reg]
    if unknown:
        raise ValueError(f"unknown operator(s): {', '.join(unknown)}; "
                         f"available: {', '.join(reg)}")
    if only:
        names = only
    else:
        names = [n for n, cls in reg.items() if cls.enabled_by_default]
    return [reg[n]() for n in names if n not in (exclude or [])]


# ---------------------------------------------------------------- engine

def in_function_body(node: Node) -> bool:
    n = node.parent
    while n is not None:
        if n.type == "compound_statement" and n.parent is not None \
                and n.parent.type == "function_definition":
            return True
        n = n.parent
    return False


def walk(node: Node):
    yield node
    for child in node.children:
        yield from walk(child)


def find_mutants(src: bytes, operators: list) -> list:
    tree = Parser(C).parse(src)
    for op in operators:
        op.prepare(tree, src)

    by_type = {}
    for op in operators:
        for t in op.node_types:
            by_type.setdefault(t, []).append(op)

    raw = []  # (Edit, operator name)
    for node in walk(tree.root_node):
        ops = by_type.get(node.type)
        if not ops or not in_function_body(node):
            continue
        for op in ops:
            for edit in op.mutate(node, src):
                raw.append((edit, op.name))

    mutants, seen = [], set()
    lines = src.decode().splitlines()
    for edit, opname in sorted(raw, key=lambda r: (r[0].start, r[0].label)):
        m = Mutant(0, opname, edit.label, src[:edit.start].count(b"\n") + 1,
                   edit.start, edit.end, edit.replacement)
        mutated = m.apply(src)
        if mutated == src or mutated in seen:
            continue
        seen.add(mutated)
        m.mid = len(mutants) + 1
        m.before = lines[m.line - 1].strip()
        if edit.replacement.strip() == ";":
            m.after = f"/* deleted */ {src[edit.start:edit.end].decode()}"
        else:
            m.after = mutated.decode().splitlines()[m.line - 1].strip()
        mutants.append(m)
    return mutants
