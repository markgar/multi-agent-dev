"""CLI app definition and command registration."""

import os
import re
from typing import Annotated

import typer

from agent.utils import console
from agent.version import get_version


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
):
    """Multi-agent autonomous development orchestrator."""

# Register commands from submodules
from agent import bootstrap as _bootstrap_mod
from agent import builder as _builder_mod
from agent import orchestrator as _orchestrator_mod
from agent import planner as _planner_mod
from agent import watcher as _watcher_mod
from agent import tester as _tester_mod
from agent import validator as _validator_mod

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
def status():
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
        console.print("=== REVIEWS ===", style="bold yellow")
        with open("REVIEWS.md", "r", encoding="utf-8") as f:
            console.print(f.read().rstrip())

    console.print()

    if os.path.exists("BUGS.md"):
        console.print("=== BUGS ===", style="bold red")
        with open("BUGS.md", "r", encoding="utf-8") as f:
            console.print(f.read().rstrip())

    console.print()
