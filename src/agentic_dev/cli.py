"""CLI app definition and command registration."""

import os
import re
from typing import Annotated

import typer

from agentic_dev.utils import console
from agentic_dev.version import get_version


def _print_dir_status(directory: str, open_prefix: str, closed_prefix: str) -> None:
    """Print open/closed item counts and list open items from a directory."""
    try:
        filenames = sorted(os.listdir(directory))
    except OSError:
        return
    open_ids = set()
    closed_ids = set()
    for name in filenames:
        if name.startswith(open_prefix) and name.endswith(".md"):
            open_ids.add(name[len(open_prefix):-3])
        elif name.startswith(closed_prefix) and name.endswith(".md"):
            closed_ids.add(name[len(closed_prefix):-3])
    still_open = open_ids - closed_ids
    console.print(f"  {len(still_open)} open, {len(closed_ids)} resolved")
    for item_id in sorted(still_open):
        console.print(f"  [ ] {open_prefix}{item_id}.md")
    for item_id in sorted(open_ids & closed_ids):
        console.print(f"  [x] {open_prefix}{item_id}.md")


def _version_callback(value: bool):
    if value:
        console.print(get_version())
        raise typer.Exit()


app = typer.Typer(
    help="Multi-agent autonomous development orchestrator using GitHub Copilot CLI.",
    no_args_is_help=True,
)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", "-v", help="Show version and exit.", callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    """Multi-agent autonomous development orchestrator."""

# Register commands from submodules
from agentic_dev import bootstrap as _bootstrap_mod
from agentic_dev import builder as _builder_mod
from agentic_dev import orchestrator as _orchestrator_mod
from agentic_dev import planner as _planner_mod
from agentic_dev import watcher as _watcher_mod
from agentic_dev import tester as _tester_mod
from agentic_dev import validator as _validator_mod

_bootstrap_mod.register(app)
_builder_mod.register(app)
_orchestrator_mod.register(app)
_planner_mod.register(app)
_watcher_mod.register(app)
_tester_mod.register(app)
_validator_mod.register(app)


# ============================================
# Commands
# ============================================


@app.command()
def status() -> None:
    """Quick view of where things stand — shows SPEC, TASKS, REVIEWS, BUGS."""
    console.print()

    if os.path.exists("SPEC.md"):
        console.print("=== SPEC ===", style="bold magenta")
        with open("SPEC.md", "r", encoding="utf-8") as f:
            content = f.read()
        console.print(content[:200], style="dim")
        console.print("...")

    console.print()

    if os.path.exists("TASKS.md"):
        console.print("=== TASKS ===", style="bold cyan")
        with open("TASKS.md", "r", encoding="utf-8") as f:
            for line in f:
                if re.search(r"\[.\]", line):
                    console.print(line.rstrip())
    else:
        console.print("No TASKS.md yet. Run 'plan' to generate it.", style="yellow")

    console.print()

    if os.path.exists("REVIEWS.md"):
        console.print("=== REVIEWS (legacy) ===", style="bold yellow")
        with open("REVIEWS.md", "r", encoding="utf-8") as f:
            console.print(f.read().rstrip())

    if os.path.isdir("reviews"):
        console.print("=== REVIEWS ===", style="bold yellow")
        _print_dir_status("reviews", "finding-", "resolved-")

    console.print()

    if os.path.exists("BUGS.md"):
        console.print("=== BUGS (legacy) ===", style="bold red")
        with open("BUGS.md", "r", encoding="utf-8") as f:
            console.print(f.read().rstrip())

    if os.path.isdir("bugs"):
        console.print("=== BUGS ===", style="bold red")
        _print_dir_status("bugs", "bug-", "fixed-")

    console.print()
