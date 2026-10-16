#!/usr/bin/env python3
"""
Minimal mutation testing for a Zephyr ztest suite on native_sim.

tree-sitter parses the C source and the enabled mutation operators
(plugins under mutators/operators, plus any --plugin files) generate
mutants. Each one is built incrementally with ninja and run as a
native_sim executable. Results are classified as:

\b
  killed      a test failed (or the image crashed)
  timeout     the image hung; counted as killed
  survived    every test still passed
  equivalent  survived AND compiled to the same machine code as the
              original (trivial compiler equivalence), so no test can kill it
  stillborn   the mutant did not compile; excluded from the score

\b
Examples:
  python3 mutate.py operators                  # show available operators
  python3 mutate.py list                       # only list the mutants
  python3 mutate.py run                        # configure, then run all
  python3 mutate.py run -o ROR,TERM            # only these operators
  python3 mutate.py run -x SDL                 # all but these
  python3 mutate.py run -p plugins/enum_swap.py
  python3 mutate.py run -b build-improved -- -DCONFIG_THERMO_TEST_IMPROVED=y
"""

import functools
import hashlib
import re
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import click
from prettytable import PrettyTable, TableStyle

from mutators import (MutationOperator, find_mutants, load_builtin_operators,
                      load_plugin, select_operators)

PASS_MARKER = "PROJECT EXECUTION SUCCESSFUL"
KILLED = ("killed", "timeout")
STATUS_COLOR = {
    "killed": "green", "timeout": "green", "survived": "red",
    "equivalent": "yellow", "stillborn": "bright_black",
}


def colored(status):
    return click.style(status, fg=STATUS_COLOR.get(status))


def table(columns, align=None):
    t = PrettyTable(columns)
    t.set_style(TableStyle.SINGLE_BORDER)
    t.align = "r"
    for col in align or []:
        t.align[col] = "l"
    return t


# ---------------------------------------------------------------- build/run

def run(cmd, timeout=None):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, timeout=timeout)


def configure(app, build, board, extra):
    if (build / "build.ninja").exists():
        return
    r = run(["cmake", "-GNinja", "-B", str(build), f"-DBOARD={board}",
             str(app), *extra])
    if r.returncode:
        raise click.ClickException(f"cmake configure failed:\n"
                                   f"{r.stdout[-3000:]}")


def build_ok(build):
    return run(["ninja", "-C", str(build)]).returncode == 0


def object_hash(build, source):
    """Hash the mutated file's object code with debug info stripped."""
    if not shutil.which("objcopy"):
        return None
    objs = list(build.rglob(f"{source.name}.obj"))
    if len(objs) != 1:
        return None
    with tempfile.NamedTemporaryFile(suffix=".o") as tmp:
        if run(["objcopy", "--strip-debug", str(objs[0]), tmp.name]).returncode:
            return None
        return hashlib.sha256(Path(tmp.name).read_bytes()).hexdigest()


def run_tests(build, timeout):
    """Returns (passed, failed_test_names). Raises TimeoutExpired."""
    r = run([str(build / "zephyr" / "zephyr.exe")], timeout=timeout)
    failed = re.findall(r"^\s*FAIL - (\S+)", r.stdout, re.M)
    passed = r.returncode == 0 and PASS_MARKER in r.stdout and not failed
    return passed, failed


def execute(mutants, source, build, timeout):
    original = source.read_bytes()
    click.echo("Baseline build and test ...")
    if not build_ok(build):
        raise click.ClickException("baseline does not build")
    passed, failed = run_tests(build, timeout)
    if not passed:
        raise click.ClickException(f"baseline tests fail ({failed}); "
                                   f"fix them first")
    baseline_hash = object_hash(build, source)

    width = len(str(len(mutants)))
    try:
        for i, m in enumerate(mutants, 1):
            source.write_bytes(m.apply(original))
            if not build_ok(build):
                m.status = "stillborn"
            else:
                try:
                    passed, m.failed_tests = run_tests(build, timeout)
                    if not passed:
                        m.status = "killed"
                    elif baseline_hash and \
                            object_hash(build, source) == baseline_hash:
                        m.status = "equivalent"
                    else:
                        m.status = "survived"
                except subprocess.TimeoutExpired:
                    m.status = "timeout"
            click.echo(f"[{i:>{width}}/{len(mutants)}] M{m.mid:<3} "
                       f"{m.operator:<5} line {m.line:<4} {colored(m.status)}")
    finally:
        source.write_bytes(original)
        build_ok(build)  # leave the build matching the real source


# ---------------------------------------------------------------- results

def score_of(mutants):
    killed = sum(m.status in KILLED for m in mutants)
    scored = killed + sum(m.status == "survived" for m in mutants)
    return killed, scored, (100.0 * killed / scored if scored else 0.0)


def per_operator(mutants):
    groups = defaultdict(list)
    for m in mutants:
        groups[m.operator].append(m)
    rows = []
    for name in sorted(groups):
        ms = groups[name]
        c = Counter(m.status for m in ms)
        killed, scored, score = score_of(ms)
        rows.append([name, len(ms), killed, c["survived"], c["equivalent"],
                     c["stillborn"], f"{score:.1f}%" if scored else "-"])
    return rows


def mutant_table(mutants, with_status):
    cols = ["#", "Line", "Op", "Change", "Mutated line"]
    if with_status:
        cols += ["Status", "Killed by"]
    t = table(cols, align=["Op", "Change", "Mutated line", "Status",
                           "Killed by"])
    t.max_width["Mutated line"] = 56
    t.max_width["Killed by"] = 36
    for m in mutants:
        row = [f"M{m.mid}", m.line, m.operator, m.label, m.after]
        if with_status:
            names = [n.split(".")[-1] for n in m.failed_tests]
            by = names[0] if names else ""
            if len(names) > 1:
                by += f" (+{len(names) - 1})"
            row += [colored(m.status), by]
        t.add_row(row)
    return t


def summary_table(mutants):
    t = table(["Operator", "Mutants", "Killed", "Survived", "Equivalent",
               "Stillborn", "Score"], align=["Operator"])
    for row in per_operator(mutants):
        t.add_row(row)
    killed, scored, score = score_of(mutants)
    c = Counter(m.status for m in mutants)
    t.add_divider()
    t.add_row(["Total", len(mutants), killed, c["survived"], c["equivalent"],
               c["stillborn"], f"{score:.1f}%"])
    return t


def write_report(path, source, mutants):
    killed, scored, score = score_of(mutants)
    c = Counter(m.status for m in mutants)
    out = [f"# Mutation report: {source}", "",
           f"Score: **{score:.1f}%** ({killed} killed of {scored} killable)  ",
           f"Equivalent: {c['equivalent']}, stillborn: {c['stillborn']}, "
           f"total: {len(mutants)}", "",
           "## Per operator", "",
           "| Operator | Mutants | Killed | Survived | Equivalent | Stillborn "
           "| Score |", "|---|---|---|---|---|---|---|"]
    for row in per_operator(mutants):
        out.append("| " + " | ".join(str(x) for x in row) + " |")

    out += ["", "## Mutants", "",
            "| # | Line | Operator | Change | Mutated line | Status | Killed by |",
            "|---|---|---|---|---|---|---|"]
    for m in mutants:
        by = ", ".join(t.split(".")[-1] for t in m.failed_tests)
        after = m.after.replace("|", "\\|")
        label = m.label.replace("|", "\\|")
        out.append(f"| {m.mid} | {m.line} | {m.operator} | {label} "
                   f"| `{after}` | {m.status} | {by} |")

    survived = [m for m in mutants if m.status == "survived"]
    if survived:
        out += ["", "## Survivors to look at", ""]
        for m in survived:
            out.append(f"- **M{m.mid}** ({m.operator}) line {m.line}: "
                       f"`{m.before}` → `{m.after}`")
    path.write_text("\n".join(out) + "\n")
    return score


# ---------------------------------------------------------------- CLI

def split_csv(ctx, param, value):
    names = [v.strip() for item in value for v in item.split(",") if v.strip()]
    return names or None


def plugin_options(f):
    """--plugin: shared by every command that needs the operator registry."""
    @click.option("-p", "--plugin", "plugins", multiple=True,
                  type=click.Path(exists=True, dir_okay=False),
                  help="Load an operator module from a file (repeatable).")
    @functools.wraps(f)
    def wrapper(plugins, **kwargs):
        load_builtin_operators()
        for p in plugins:
            load_plugin(p)
        return f(**kwargs)
    return wrapper


def mutant_options(f):
    """Options that decide which mutants are generated."""
    @click.option("-a", "--app", default=".", show_default=True,
                  type=click.Path(exists=True, file_okay=False),
                  help="Zephyr app/test directory.")
    @click.option("-s", "--source", default="src/thermo.c", show_default=True,
                  help="File to mutate, relative to --app.")
    @click.option("-o", "--operators", multiple=True, callback=split_csv,
                  help="Operators to run, comma-separated or repeated "
                       "(default: all enabled by default).")
    @click.option("-x", "--exclude", multiple=True, callback=split_csv,
                  help="Operators to skip, comma-separated or repeated.")
    @plugin_options
    @functools.wraps(f)
    def wrapper(app, source, operators, exclude, **kwargs):
        try:
            ops = select_operators(operators, exclude or [])
        except ValueError as e:
            raise click.BadParameter(str(e), param_hint="--operators/--exclude")
        app = Path(app).resolve()
        src = app / source
        if not src.is_file():
            raise click.BadParameter(f"{src} not found", param_hint="--source")
        mutants = find_mutants(src.read_bytes(), ops)
        click.echo(f"Operators: {', '.join(op.name for op in ops)}")
        return f(app=app, source=src, source_rel=source, mutants=mutants,
                 **kwargs)
    return wrapper


@click.group(help=__doc__, context_settings={"help_option_names":
                                             ["-h", "--help"]})
def cli():
    pass


@cli.command("operators")
@plugin_options
def list_operators():
    """List the available mutation operators."""
    t = table(["Name", "Default", "Description"],
              align=["Name", "Default", "Description"])
    for name, cls in MutationOperator.registry.items():
        t.add_row([name, "on" if cls.enabled_by_default else "off",
                   cls.description])
    click.echo(t)


@cli.command("list")
@mutant_options
def list_mutants(app, source, source_rel, mutants):
    """List the mutants without building or running anything."""
    click.echo(mutant_table(mutants, with_status=False))
    click.echo(f"{len(mutants)} mutants")


@cli.command("run", context_settings={"ignore_unknown_options": True})
@mutant_options
@click.option("-B", "--board", default="native_sim/native/64",
              show_default=True, help="Zephyr board target.")
@click.option("-b", "--build-dir", default="build-mutation", show_default=True,
              type=click.Path(file_okay=False),
              help="Build directory, reused between runs.")
@click.option("-t", "--timeout", default=10.0, show_default=True,
              help="Seconds per test run.")
@click.option("-r", "--report", default="mutation_report.md",
              show_default=True, type=click.Path(dir_okay=False),
              help="Markdown report to write.")
@click.option("--fail-under", type=click.FloatRange(0, 100), default=None,
              help="Exit with status 2 if the score is below this "
                   "percentage (for CI).")
@click.argument("cmake_args", nargs=-1, type=click.UNPROCESSED)
def run_mutants(app, source, source_rel, mutants, board, build_dir, timeout,
                report, fail_under, cmake_args):
    """Build and test every mutant. Extra CMake args go after `--`."""
    build = Path(build_dir).resolve()
    configure(app, build, board, list(cmake_args))
    execute(mutants, source, build, timeout)

    click.echo()
    click.echo(mutant_table(mutants, with_status=True))
    click.echo()
    click.echo(summary_table(mutants))
    score = write_report(Path(report), source_rel, mutants)
    click.echo(f"\nMutation score: {click.style(f'{score:.1f}%', bold=True)}"
               f"  (report: {report})")
    if fail_under is not None and score < fail_under:
        raise click.exceptions.Exit(2)


if __name__ == "__main__":
    cli()
