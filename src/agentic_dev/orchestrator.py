"""Orchestrator: the 'go' command that detects, bootstraps, and coordinates all agents."""

import os
import re
from datetime import datetime, timezone
from typing import Annotated

import typer

from agentic_dev.bootstrap import run_bootstrap, write_workspace_readme
from agentic_dev.builder import build
from agentic_dev.planner import check_milestone_sizes, plan
from agentic_dev.prompts import (
    COPILOT_INSTRUCTIONS_PROMPT,
    COPILOT_INSTRUCTIONS_TEMPLATE,
)
from agentic_dev.sentinel import clear_builder_done
from agentic_dev.terminal import spawn_agent_in_terminal
from agentic_dev.utils import console, log, pushd, run_cmd, run_copilot, validate_model


def register(app: typer.Typer) -> None:
    """Register orchestrator commands on the shared app."""
    app.command()(go)


# ============================================
# Clone and repo detection helpers
# ============================================


def _detect_clone_source(parent_dir: str) -> str:
    """Determine the git clone source for creating missing agent clones.

    Checks for a local bare repo first, then reads the remote URL from the builder clone.
    Returns empty string if neither is found.
    """
    bare_repo = os.path.join(parent_dir, "remote.git")
    if os.path.exists(bare_repo):
        return bare_repo
    builder_dir = os.path.join(parent_dir, "builder")
    if not os.path.exists(builder_dir):
        return ""
    with pushd(builder_dir):
        result = run_cmd(["git", "remote", "get-url", "origin"], capture=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return ""


def _find_existing_repo(parent_dir: str, name: str, local: bool) -> str:
    """Check if the project repo already exists. Returns the clone URL/path, or empty string.

    Local mode: checks for <parent_dir>/remote.git.
    GitHub mode: checks for the repo on GitHub via gh repo view.
    """
    if local:
        bare_repo = os.path.join(parent_dir, "remote.git")
        if os.path.exists(bare_repo):
            return bare_repo
        return ""

    result = run_cmd(["gh", "api", "user", "--jq", ".login"], capture=True)
    gh_user = result.stdout.strip() if result.returncode == 0 else ""
    if not gh_user:
        return ""
    repo_check = run_cmd(["gh", "repo", "view", f"{gh_user}/{name}"], quiet=True)
    if repo_check.returncode == 0:
        return f"https://github.com/{gh_user}/{name}"
    return ""


def _clone_all_agents(parent_dir: str, clone_source: str) -> None:
    """Clone any missing agent directories from the given source."""
    os.makedirs(parent_dir, exist_ok=True)
    for agent in ["builder", "reviewer", "tester", "validator"]:
        agent_dir = os.path.join(parent_dir, agent)
        if not os.path.exists(agent_dir):
            log("orchestrator", f"Cloning {agent} from existing repo...", style="cyan")
            with pushd(parent_dir):
                run_cmd(["git", "clone", clone_source, agent])
    write_workspace_readme(parent_dir)


def _pull_all_clones(parent_dir: str) -> None:
    """Pull latest on all agent clones. Create any missing clones."""
    clone_source = _detect_clone_source(parent_dir)

    for agent in ["builder", "reviewer", "tester", "validator"]:
        agent_dir = os.path.join(parent_dir, agent)
        if not os.path.exists(agent_dir):
            if clone_source:
                log("orchestrator", f"{agent} clone not found — creating it...", style="yellow")
                with pushd(parent_dir):
                    run_cmd(["git", "clone", clone_source, agent])
            else:
                log("orchestrator", f"WARNING: Could not determine clone source for {agent}.", style="yellow")
        else:
            with pushd(agent_dir):
                run_cmd(["git", "pull", "--rebase"], quiet=True)


# ============================================
# Requirements and copilot-instructions helpers
# ============================================


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


# ============================================
# Agent launching and build orchestration
# ============================================


def _launch_agents_and_build(parent_dir: str, plan_label: str, requirements_changed: bool = False) -> None:
    """Run planner, spawn reviewer/tester in terminals, then build until done."""
    clear_builder_done()

    log("orchestrator", "")
    log("orchestrator", "======================================", style="bold magenta")
    log("orchestrator", f" {plan_label}", style="bold magenta")
    log("orchestrator", "======================================", style="bold magenta")
    plan(requirements_changed=requirements_changed)
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


# ============================================
# Input resolution helpers
# ============================================


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


def _resolve_directory(directory: str) -> str | None:
    """Resolve the --directory option to an absolute path.

    For new projects the directory doesn't need to exist yet.
    For existing projects it validates the path exists.
    Returns the resolved absolute path, or None on error.
    """
    resolved = os.path.abspath(os.path.expanduser(directory))
    return resolved


# ============================================
# The 'go' command
# ============================================


def _bootstrap_new_project(
    parent_dir: str, project_name: str, description: str, spec_file: str, local: bool, start_dir: str,
) -> None:
    """Bootstrap a brand-new project: create repo, plan, and launch agents."""
    if not description and not spec_file:
        console.print("ERROR: New project requires --description or --spec-file.", style="bold red")
        return

    run_bootstrap(directory=parent_dir, name=project_name, description=description, spec_file=spec_file, local=local)
    if not os.path.exists(os.path.join(parent_dir, "builder")):
        log("orchestrator", "ERROR: Bootstrap did not create the expected directory structure.", style="bold red")
        os.chdir(start_dir)
        return

    os.chdir(os.path.join(parent_dir, "builder"))
    _launch_agents_and_build(parent_dir, "Running backlog planner...")


def _resume_existing_project(
    parent_dir: str, project_name: str, repo_source: str, description: str, spec_file: str,
) -> None:
    """Resume an existing project: clone agents, update requirements if needed, and build."""
    new_description = _resolve_description_optional(description, spec_file)

    log("orchestrator", "")
    log("orchestrator", "======================================", style="bold cyan")
    if new_description:
        log("orchestrator", f" Continuing project '{project_name}' with new requirements", style="bold cyan")
    else:
        log("orchestrator", f" Continuing project '{project_name}'", style="bold cyan")
    log("orchestrator", "======================================", style="bold cyan")

    _clone_all_agents(parent_dir, repo_source)
    _pull_all_clones(parent_dir)
    os.chdir(os.path.join(parent_dir, "builder"))

    if new_description:
        _update_requirements(os.path.join(parent_dir, "builder"), new_description)

    _launch_agents_and_build(parent_dir, "Running milestone planner...", requirements_changed=bool(new_description))


def go(
    directory: Annotated[str, typer.Option(help="Project directory path (created if new, resumed if existing)")],
    model: Annotated[str, typer.Option(help="Copilot model to use (required). Allowed: GPT-5.3-Codex, Claude Opus 4.6")],
    description: Annotated[str, typer.Option(help="What the project should do")] = None,
    spec_file: Annotated[str, typer.Option(help="Path to a markdown file containing the project requirements")] = None,
    local: Annotated[bool, typer.Option(help="Use a local bare git repo instead of GitHub")] = False,
    name: Annotated[str, typer.Option(help="GitHub repo name (defaults to directory basename)")] = None,
) -> None:
    """Start or continue a project. Detects whether the project already exists.

    New project:      bootstraps, plans, and launches all agents.
    Existing project: pulls latest, optionally updates requirements, re-plans, and builds.

    --directory is the project working directory — relative or absolute.
    --name optionally overrides the GitHub repo name (defaults to basename of directory).
    """
    validate_model(model)
    os.environ["COPILOT_MODEL"] = model
    console.print(f"Using model: {model}", style="bold green")

    start_dir = os.getcwd()

    # --- Resolve project directory ---
    parent_dir = _resolve_directory(directory)
    if parent_dir is None:
        return

    project_name = name or os.path.basename(parent_dir)

    # --- Check if the repo already exists (locally or on GitHub) ---
    repo_source = _find_existing_repo(parent_dir, project_name, local)

    if not repo_source:
        _bootstrap_new_project(parent_dir, project_name, description, spec_file, local, start_dir)
    else:
        _resume_existing_project(parent_dir, project_name, repo_source, description, spec_file)

    os.chdir(start_dir)
