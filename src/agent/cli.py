"""CLI commands for the multi-agent development orchestrator."""

import os
import re
from typing import Annotated

import typer

from agent.prompts import PLANNER_PROMPT
from agent.sentinel import clear_builder_done
from agent.utils import console, log, pushd, run_cmd, run_copilot

app = typer.Typer(
    help="Multi-agent autonomous development orchestrator using GitHub Copilot CLI.",
    no_args_is_help=True,
)

# Register commands from submodules
from agent import bootstrap as _bootstrap_mod
from agent import builder as _builder_mod
from agent import watcher as _watcher_mod
from agent import tester as _tester_mod

_bootstrap_mod.register(app)
_builder_mod.register(app)
_watcher_mod.register(app)
_tester_mod.register(app)

# Re-export for internal use by builder (which calls plan() in its loop)
from agent.bootstrap import run_bootstrap
from agent.builder import build, check_milestone_sizes
from agent.terminal import spawn_agent_in_terminal


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


@app.command()
def plan():
    """Run the planner to create or update TASKS.md based on SPEC.md."""
    log("planner", "")
    log("planner", "[Planner] Evaluating project state...", style="magenta")
    log("planner", "")

    exit_code = run_copilot("planner", PLANNER_PROMPT)

    if exit_code != 0:
        log("planner", "")
        log("planner", "======================================", style="bold red")
        log("planner", " Planner failed! Check errors above", style="bold red")
        log("planner", "======================================", style="bold red")
        return

    log("planner", "")
    log("planner", "======================================", style="bold magenta")
    log("planner", " Plan updated!", style="bold magenta")
    log("planner", "======================================", style="bold magenta")


def _launch_agents_and_build(parent_dir: str, plan_label: str) -> None:
    """Run planner, spawn reviewer/tester in terminals, then build until done."""
    clear_builder_done()

    log("orchestrator", "")
    log("orchestrator", "======================================", style="bold magenta")
    log("orchestrator", f" {plan_label}", style="bold magenta")
    log("orchestrator", "======================================", style="bold magenta")
    plan()
    check_milestone_sizes()

    log("orchestrator", "")
    log("orchestrator", "Launching commit watcher (per-commit reviewer)...", style="yellow")
    spawn_agent_in_terminal(os.path.join(parent_dir, "reviewer"), "commitwatch")

    log("orchestrator", "Launching tester (milestone-triggered)...", style="yellow")
    spawn_agent_in_terminal(os.path.join(parent_dir, "tester"), "testloop")

    log("orchestrator", "")
    log("orchestrator", "======================================", style="bold green")
    log("orchestrator", " All agents launched! Building...", style="bold green")
    log("orchestrator", "======================================", style="bold green")
    log("orchestrator", "")
    build(loop=True)


@app.command()
def go(
    name: Annotated[str, typer.Option(help="Project name")],
    description: Annotated[str, typer.Option(help="What the project should do")] = None,
    language: Annotated[str, typer.Option(help="Language/stack: dotnet, python, node")] = "node",
    spec_file: Annotated[str, typer.Option(help="Path to a markdown file containing the project requirements")] = None,
):
    """One command to rule them all: bootstrap, plan, and launch all agents."""
    start_dir = os.getcwd()

    run_bootstrap(name=name, description=description, language=language, spec_file=spec_file)
    if not os.path.exists(os.path.join(os.getcwd(), "builder")):
        log("orchestrator", "ERROR: Bootstrap did not create the expected directory structure.", style="bold red")
        os.chdir(start_dir)
        return

    parent_dir = os.getcwd()
    os.chdir(os.path.join(parent_dir, "builder"))

    _launch_agents_and_build(parent_dir, "Running planner...")

    os.chdir(start_dir)


@app.command()
def resume(
    name: Annotated[str, typer.Option(help="Project name (existing project directory)")],
):
    """Pick up where you left off: re-plan, launch watchers, resume building."""
    start_dir = os.getcwd()
    parent_dir = os.path.join(os.getcwd(), name)

    if not os.path.exists(os.path.join(parent_dir, "builder")):
        log(
            "orchestrator",
            f"ERROR: Could not find builder directory under {parent_dir}. Are you in the right directory?",
            style="bold red",
        )
        return

    os.chdir(os.path.join(parent_dir, "builder"))
    run_cmd(["git", "pull", "--rebase"], quiet=True)

    reviewer_dir = os.path.join(parent_dir, "reviewer")
    tester_dir = os.path.join(parent_dir, "tester")
    with pushd(reviewer_dir):
        run_cmd(["git", "pull", "--rebase"], quiet=True)
    with pushd(tester_dir):
        run_cmd(["git", "pull", "--rebase"], quiet=True)

    _launch_agents_and_build(parent_dir, "Re-evaluating plan...")

    os.chdir(start_dir)
