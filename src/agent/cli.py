"""CLI commands for the multi-agent development orchestrator."""

import os
import re
from datetime import datetime, timezone
from typing import Annotated

import typer

from agent.prompts import COPILOT_INSTRUCTIONS_PROMPT, COPILOT_INSTRUCTIONS_TEMPLATE, PLANNER_PROMPT
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
from agent import validator as _validator_mod

_bootstrap_mod.register(app)
_builder_mod.register(app)
_watcher_mod.register(app)
_tester_mod.register(app)
_validator_mod.register(app)

# Re-export for internal use by builder (which calls plan() in its loop)
from agent.bootstrap import run_bootstrap
from agent.builder import build, check_milestone_sizes
from agent.terminal import spawn_agent_in_terminal


def _detect_clone_source(parent_dir: str) -> str:
    """Determine the git clone source for creating missing agent clones.

    Checks for a local bare repo first, then reads the remote URL from the builder clone.
    Returns empty string if neither is found.
    """
    bare_repo = os.path.join(parent_dir, "remote.git")
    if os.path.exists(bare_repo):
        return bare_repo
    builder_dir = os.path.join(parent_dir, "builder")
    with pushd(builder_dir):
        result = run_cmd(["git", "remote", "get-url", "origin"], capture=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return ""


def _pull_all_clones(parent_dir: str) -> None:
    """Pull latest on all agent clones. Create validator clone if missing."""
    builder_dir = os.path.join(parent_dir, "builder")
    reviewer_dir = os.path.join(parent_dir, "reviewer")
    tester_dir = os.path.join(parent_dir, "tester")
    validator_dir = os.path.join(parent_dir, "validator")

    with pushd(builder_dir):
        run_cmd(["git", "pull", "--rebase"], quiet=True)
    with pushd(reviewer_dir):
        run_cmd(["git", "pull", "--rebase"], quiet=True)
    with pushd(tester_dir):
        run_cmd(["git", "pull", "--rebase"], quiet=True)

    if not os.path.exists(validator_dir):
        log("orchestrator", "Validator clone not found — creating it...", style="yellow")
        clone_source = _detect_clone_source(parent_dir)
        if clone_source:
            with pushd(parent_dir):
                run_cmd(["git", "clone", clone_source, "validator"])
        else:
            log("orchestrator", "WARNING: Could not determine clone source for validator.", style="yellow")
    else:
        with pushd(validator_dir):
            run_cmd(["git", "pull", "--rebase"], quiet=True)


def _update_requirements(builder_dir: str, description: str) -> None:
    """Overwrite REQUIREMENTS.md with new requirements, commit, pull, and push."""
    req_path = os.path.join(builder_dir, "REQUIREMENTS.md")
    with open(req_path, "w", encoding="utf-8") as f:
        f.write("# Project Requirements\n\n")
        f.write("> This document contains the project requirements as provided by the user.\n")
        f.write("> It may be updated with new requirements in later sessions.\n\n")
        f.write(description)
        f.write("\n")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with pushd(builder_dir):
        run_cmd(["git", "add", "REQUIREMENTS.md"])
        run_cmd(["git", "commit", "-m", f"Update requirements ({timestamp})"])
        run_cmd(["git", "pull", "--rebase"], quiet=True)
        run_cmd(["git", "push"])

    log("orchestrator", "Updated REQUIREMENTS.md with new requirements.", style="green")


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


def _generate_copilot_instructions() -> None:
    """Generate .github/copilot-instructions.md from SPEC.md and TASKS.md."""
    if os.path.exists(os.path.join(".github", "copilot-instructions.md")):
        log("orchestrator", "copilot-instructions.md already exists, skipping generation.", style="dim")
        return

    log("orchestrator", "")
    log("orchestrator", "[Orchestrator] Generating copilot-instructions.md...", style="magenta")

    template_for_prompt = COPILOT_INSTRUCTIONS_TEMPLATE.replace("{", "{{").replace("}", "}}")
    template_for_prompt = template_for_prompt.replace("{{project_structure}}", "{project_structure}")
    template_for_prompt = template_for_prompt.replace("{{key_files}}", "{key_files}")
    template_for_prompt = template_for_prompt.replace("{{architecture}}", "{architecture}")
    template_for_prompt = template_for_prompt.replace("{{conventions}}", "{conventions}")

    prompt = COPILOT_INSTRUCTIONS_PROMPT.format(template=template_for_prompt)
    exit_code = run_copilot("orchestrator", prompt)

    if exit_code == 0:
        log("orchestrator", "copilot-instructions.md generated.", style="green")
    else:
        log("orchestrator", "WARNING: Failed to generate copilot-instructions.md. Continuing.", style="yellow")


def _launch_agents_and_build(parent_dir: str, plan_label: str) -> None:
    """Run planner, spawn reviewer/tester in terminals, then build until done."""
    clear_builder_done()

    log("orchestrator", "")
    log("orchestrator", "======================================", style="bold magenta")
    log("orchestrator", f" {plan_label}", style="bold magenta")
    log("orchestrator", "======================================", style="bold magenta")
    plan()
    check_milestone_sizes()
    _generate_copilot_instructions()

    log("orchestrator", "")
    log("orchestrator", "Launching commit watcher (per-commit reviewer)...", style="yellow")
    spawn_agent_in_terminal(os.path.join(parent_dir, "reviewer"), "commitwatch")

    log("orchestrator", "Launching tester (milestone-triggered)...", style="yellow")
    spawn_agent_in_terminal(os.path.join(parent_dir, "tester"), "testloop")

    log("orchestrator", "Launching validator (milestone-triggered)...", style="yellow")
    spawn_agent_in_terminal(os.path.join(parent_dir, "validator"), "validateloop")

    log("orchestrator", "")
    log("orchestrator", "======================================", style="bold green")
    log("orchestrator", " All agents launched! Building...", style="bold green")
    log("orchestrator", "======================================", style="bold green")
    log("orchestrator", "")
    build(loop=True)


def _resolve_description_optional(description, spec_file):
    """Resolve project description from --description or --spec-file. Returns None if neither provided."""
    if spec_file and description:
        console.print("ERROR: Provide --description or --spec-file, not both.", style="bold red")
        raise typer.Exit(1)
    if spec_file:
        spec_path = os.path.expanduser(spec_file)
        if not os.path.isfile(spec_path):
            console.print(f"ERROR: Spec file not found: {spec_path}", style="bold red")
            raise typer.Exit(1)
        with open(spec_path, "r", encoding="utf-8") as f:
            description = f.read().strip()
        if not description:
            console.print("ERROR: Spec file is empty.", style="bold red")
            raise typer.Exit(1)
        console.print(f"Using requirements from: {spec_path}", style="cyan")
    return description


@app.command()
def go(
    directory: Annotated[str, typer.Option(help="Project directory path (created if new, resumed if existing)")],
    description: Annotated[str, typer.Option(help="What the project should do")] = None,
    spec_file: Annotated[str, typer.Option(help="Path to a markdown file containing the project requirements")] = None,
    local: Annotated[bool, typer.Option(help="Use a local bare git repo instead of GitHub")] = False,
    name: Annotated[str, typer.Option(help="GitHub repo name (defaults to directory basename)")] = None,
):
    """Start or continue a project. Detects whether the project already exists.

    New project:      bootstraps, plans, and launches all agents.
    Existing project: pulls latest, optionally updates requirements, re-plans, and builds.

    --directory is the project working directory — relative or absolute.
    --name optionally overrides the GitHub repo name (defaults to basename of directory).
    """
    start_dir = os.getcwd()

    # --- Resolve project directory ---
    parent_dir = _resolve_directory(directory)
    if parent_dir is None:
        return

    project_name = name or os.path.basename(parent_dir)
    project_exists = os.path.exists(os.path.join(parent_dir, "builder"))

    if not project_exists:
        # --- New project: full bootstrap ---
        if not description and not spec_file:
            console.print("ERROR: New project requires --description or --spec-file.", style="bold red")
            return

        run_bootstrap(directory=parent_dir, name=project_name, description=description, spec_file=spec_file, local=local)
        if not os.path.exists(os.path.join(parent_dir, "builder")):
            log("orchestrator", "ERROR: Bootstrap did not create the expected directory structure.", style="bold red")
            os.chdir(start_dir)
            return

        os.chdir(os.path.join(parent_dir, "builder"))
        _launch_agents_and_build(parent_dir, "Running planner...")

    else:
        # --- Existing project: continue or iterate ---
        new_description = _resolve_description_optional(description, spec_file)

        log("orchestrator", "")
        log("orchestrator", "======================================", style="bold cyan")
        if new_description:
            log("orchestrator", f" Continuing project '{project_name}' with new requirements", style="bold cyan")
        else:
            log("orchestrator", f" Continuing project '{project_name}'", style="bold cyan")
        log("orchestrator", "======================================", style="bold cyan")

        _pull_all_clones(parent_dir)
        os.chdir(os.path.join(parent_dir, "builder"))

        if new_description:
            _update_requirements(os.path.join(parent_dir, "builder"), new_description)

        _launch_agents_and_build(parent_dir, "Evaluating plan...")

    os.chdir(start_dir)


def _resolve_directory(directory: str) -> str | None:
    """Resolve the --directory option to an absolute path.

    For new projects the directory doesn't need to exist yet.
    For existing projects it validates the path exists.
    Returns the resolved absolute path, or None on error.
    """
    resolved = os.path.abspath(os.path.expanduser(directory))
    return resolved
