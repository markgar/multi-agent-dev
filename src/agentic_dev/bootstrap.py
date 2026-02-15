"""Bootstrap command: scaffold a new project repo and clone reviewer/tester copies."""

import os
from typing import Annotated

import typer

from agentic_dev.prompts import BOOTSTRAP_PROMPT, LOCAL_BOOTSTRAP_PROMPT
from agentic_dev.utils import (
    check_command,
    console,
    is_macos,
    log,
    run_cmd,
    run_copilot,
)


def register(app: typer.Typer) -> None:
    """Register bootstrap commands on the shared app."""
    app.command(hidden=True, deprecated=True)(bootstrap)


def bootstrap(
    name: Annotated[str, typer.Option(help="Project name (used for directory and GitHub repo)")],
    description: Annotated[str, typer.Option(help="What the project should do")] = None,
    spec_file: Annotated[str, typer.Option(help="Path to a markdown file containing the project requirements")] = None,
) -> None:
    """Deprecated: use 'go' instead. Bootstrap only scaffolds — it does NOT launch the planner, builder, or watchers."""
    console.print()
    console.print("======================================", style="bold red")
    console.print(" ERROR: Don't use 'bootstrap' directly!", style="bold red")
    console.print("======================================", style="bold red")
    console.print()
    console.print("'bootstrap' only scaffolds the repo — it does NOT launch the", style="yellow")
    console.print("planner, builder, commit watcher, or tester.", style="yellow")
    console.print()
    console.print("Use 'go' instead, which does everything end-to-end:", style="green")
    console.print()
    console.print("  agentic-dev go --directory <path> --spec-file <file>", style="bold cyan")
    console.print("  agentic-dev go --directory <path> --description \"...\"", style="bold cyan")
    console.print()
    console.print("To continue an existing project with new requirements:", style="green")
    console.print()
    console.print("  agentic-dev go --directory <path> --spec-file <new-features.md>", style="bold cyan")
    console.print()
    raise typer.Exit(1)


def _resolve_description(description, spec_file):
    """Resolve project description from --description or --spec-file (mutually exclusive)."""
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
    if not description:
        console.print("ERROR: Provide either --description or --spec-file.", style="bold red")
        raise typer.Exit(1)
    return description


def _check_required_tools(local: bool) -> bool:
    """Verify required CLI tools are installed. Returns True if all present."""
    tools = [("git", "brew install git", "winget install Git.Git"), ("docker", "brew install --cask docker", "winget install Docker.DockerDesktop"), ("copilot", None, None)]
    if not local:
        tools.insert(1, ("gh", "brew install gh", "winget install GitHub.cli"))
    for tool, install_mac, install_win in tools:
        if not check_command(tool):
            console.print(f"ERROR: {tool} is not installed.", style="bold red")
            install = install_mac if is_macos() else install_win
            if install:
                console.print(f"Run: {install}", style="yellow")
            console.print("Then close and reopen your terminal.", style="yellow")
            return False
        console.print(f"✓ {tool:<8} - OK", style="green")
    return True


def _check_prerequisites(local=False):
    """Check all prerequisites (GitHub user, core tools, auth). Returns gh_user or None."""
    if local:
        gh_user = "local"
    else:
        result = run_cmd(["gh", "api", "user", "--jq", ".login"], capture=True)
        gh_user = result.stdout.strip() if result.returncode == 0 else ""
        if not gh_user:
            console.print("ERROR: Could not determine GitHub username.", style="bold red")
            console.print("Run: gh auth login", style="yellow")
            return None

    if not _check_required_tools(local):
        return None

    if not local:
        auth_result = run_cmd(["gh", "auth", "status"], quiet=True)
        if auth_result.returncode != 0:
            console.print("ERROR: GitHub CLI is not authenticated.", style="bold red")
            console.print("Run: gh auth login", style="yellow")
            return None
        console.print("✓ gh auth  - OK (authenticated)", style="green")

    return gh_user


_WORKSPACE_README = """# Multi-Agent Workspace

This directory is managed by the **agentic-dev** multi-agent orchestrator.
It is not the project source code itself — it is the workspace that contains
separate clones of the project repo, each used by a different agent.

## Directory Structure

| Directory | Purpose |
|---|---|
| `builder/` | Builder agent — writes code, fixes bugs, completes milestones |
| `reviewer/` | Reviewer agent — reviews each commit and milestone for quality |
| `tester/` | Tester agent — runs scoped tests after each milestone |
| `validator/` | Validator agent — builds Docker containers and validates against spec |
| `remote.git/` | Local bare git repo (local mode only; replaced by GitHub in production) |
| `logs/` | Agent logs, checkpoints, and coordination signals |

Each agent directory is an independent git clone of the same repo.
They coordinate through git push/pull and shared markdown files.

## Key Files (inside each clone)

| File | Purpose |
|---|---|
| `SPEC.md` | Technical decisions — architecture, tech stack, cross-cutting concerns |
| `BACKLOG.md` | Ordered story queue with dependency tracking (planner-managed) |
| `TASKS.md` | Current and completed milestones — checked off as work is completed |
| `REQUIREMENTS.md` | Original user requirements (may be updated between sessions) |
| `BUGS.md` | Bugs found by the tester and validator |
| `REVIEWS.md` | Code review findings from the reviewer |
| `DEPLOY.md` | Deployment knowledge accumulated by the validator |
| `.github/copilot-instructions.md` | Coding guidelines and project conventions for the builder |

## Log Files

| File | What it captures |
|---|---|
| `logs/builder.log` | Every Copilot invocation — prompts and output |
| `logs/planner.log` | Planner decisions and task list changes |
| `logs/reviewer.log` | Per-commit and milestone reviews |
| `logs/tester.log` | Test runs and bug reports |
| `logs/validator.log` | Container builds and acceptance test results |
| `logs/milestones.log` | Milestone boundaries (name, start SHA, end SHA) |
| `logs/orchestrator.log` | High-level orchestration status |
| `logs/builder.done` | Sentinel file — signals all agents to shut down |
| `logs/reviewer.checkpoint` | Last-reviewed commit SHA |
| `logs/reviewer.milestone` | Set of milestones already reviewed |
| `logs/tester.milestone` | Set of milestones already tested |
| `logs/validator.milestone` | Set of milestones already validated |

## How It Works

1. The **planner** reads SPEC.md and REQUIREMENTS.md, creates BACKLOG.md (story queue) and one milestone in TASKS.md
2. The **builder** completes one milestone at a time, committing after each task
3. The **reviewer** watches for new commits and reviews them for quality
4. The **tester** runs scoped tests when a milestone completes
5. The **validator** builds the app in Docker and tests against SPEC.md acceptance criteria
6. After each milestone, the **planner** expands the next backlog story into a new milestone
7. When the backlog is empty and all agents are idle, the builder writes `logs/builder.done` and everyone shuts down

Agent directories are disposable — they can be deleted and re-cloned from the repo at any time.
The repo and `logs/` directory are the persistent state.
"""


def write_workspace_readme(directory: str) -> None:
    """Write a README.md in the workspace root describing the multi-agent structure."""
    readme_path = os.path.join(directory, "README.md")
    try:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(_WORKSPACE_README)
    except Exception:
        pass


def _write_requirements_file(builder_dir: str, description: str) -> None:
    """Create builder/REQUIREMENTS.md with the user's project description."""
    req_path = os.path.join(builder_dir, "REQUIREMENTS.md")
    with open(req_path, "w", encoding="utf-8") as f:
        f.write("# Project Requirements\n\n")
        f.write("> This document contains the project requirements as provided by the user.\n")
        f.write("> It may be updated with new requirements in later sessions.\n\n")
        f.write(description)
        f.write("\n")
    console.print("✓ Saved original requirements to REQUIREMENTS.md", style="green")


def _clone_agent_copies(local: bool, gh_user: str, name: str) -> None:
    """Clone reviewer, tester, and validator copies from the repo."""
    if local:
        clone_source = os.path.join(os.getcwd(), "remote.git")
    else:
        clone_source = f"https://github.com/{gh_user}/{name}"
    log("bootstrap", "")
    for agent_name in ("reviewer", "tester", "validator"):
        log("bootstrap", f"Cloning {agent_name} copy...", style="cyan")
        run_cmd(["git", "clone", clone_source, agent_name])


def _scaffold_project(directory, name, description, gh_user, local=False):
    """Create repo, write REQUIREMENTS.md, run Copilot bootstrap, clone reviewer/tester.

    directory: absolute path to the project parent directory.
    name: project name (used for GitHub repo name in non-local mode).
    Returns True on success.
    """
    if not local:
        repo_check = run_cmd(["gh", "repo", "view", f"{gh_user}/{name}"], quiet=True)
        if repo_check.returncode == 0:
            console.print(f"ERROR: Repository {gh_user}/{name} already exists on GitHub.", style="bold red")
            console.print(
                f"Delete it first (gh repo delete {gh_user}/{name}) or choose a different name.",
                style="yellow",
            )
            return False

    os.makedirs(directory, exist_ok=True)
    os.chdir(directory)

    # Write workspace README immediately so the directory is self-documenting
    write_workspace_readme(os.getcwd())

    # Create local bare repo when running in local mode (no GitHub)
    if local:
        bare_repo_path = os.path.join(os.getcwd(), "remote.git")
        run_cmd(["git", "init", "--bare", bare_repo_path])
        console.print("✓ Created local bare repo at remote.git", style="green")

    builder_dir = os.path.join(os.getcwd(), "builder")
    os.makedirs(builder_dir, exist_ok=True)
    _write_requirements_file(builder_dir, description)

    if local:
        remote_path = os.path.join(os.getcwd(), "remote.git")
        prompt = LOCAL_BOOTSTRAP_PROMPT.format(description=description, remote_path=remote_path)
    else:
        prompt = BOOTSTRAP_PROMPT.format(description=description, gh_user=gh_user, name=name)
    exit_code = run_copilot("bootstrap", prompt)

    if exit_code != 0:
        log("bootstrap", "")
        log("bootstrap", "======================================", style="bold red")
        log("bootstrap", " Bootstrap failed! Check errors above", style="bold red")
        log("bootstrap", "======================================", style="bold red")
        return False

    _clone_agent_copies(local, gh_user, name)

    write_workspace_readme(os.getcwd())

    log("bootstrap", "")
    log("bootstrap", "======================================", style="bold green")
    log("bootstrap", " Bootstrap complete!", style="bold green")
    log("bootstrap", "======================================", style="bold green")
    return True


def run_bootstrap(
    directory: str,
    name: str,
    description: str = None,
    spec_file: str = None,
    local: bool = False,
) -> None:
    """Internal: scaffold a new project — git repo, GitHub remote (or local bare repo), clone reviewer/tester copies.

    directory: absolute path to the project parent directory.
    name: project name (used for GitHub repo name, display labels).
    """
    description = _resolve_description(description, spec_file)

    current_dir = os.path.basename(os.getcwd())
    abs_directory = os.path.normcase(os.path.abspath(directory))
    abs_cwd = os.path.normcase(os.path.abspath(os.getcwd()))
    directory_is_subdirectory = abs_directory.startswith(abs_cwd + os.sep)
    if current_dir == "multi-agent-dev" and not directory_is_subdirectory:
        console.print()
        console.print("WARNING: You are in the multi-agent-dev directory.", style="yellow")
        console.print("Project will be created at:", style="yellow")
        console.print(f"  {directory}/", style="cyan")
        console.print()
        response = typer.prompt("Are you sure you want to continue? (y/N)")
        if not response.strip().lower().startswith("y"):
            console.print("Bootstrap cancelled.", style="yellow")
            return

    gh_user = _check_prerequisites(local=local)
    if not gh_user:
        return

    mode_label = " (local mode)" if local else ""
    console.print()
    console.print(f"Bootstrapping {name}{mode_label}...", style="cyan")
    console.print()

    if not _scaffold_project(directory, name, description, gh_user, local=local):
        return
