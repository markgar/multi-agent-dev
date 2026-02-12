"""Bootstrap command: scaffold a new project repo and clone reviewer/tester copies."""

import os
from typing import Annotated

import typer

from agent.config import LANGUAGE_CONFIGS, VALID_LANGUAGES
from agent.prompts import BOOTSTRAP_PROMPT, LOCAL_BOOTSTRAP_PROMPT
from agent.utils import (
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
    language: Annotated[str, typer.Option(help="Language/stack: dotnet, python, node")] = "node",
    spec_file: Annotated[str, typer.Option(help="Path to a markdown file containing the project requirements")] = None,
):
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
    console.print("  agentic-dev go --name <project> --spec-file <file>", style="bold cyan")
    console.print("  agentic-dev go --name <project> --description \"...\"", style="bold cyan")
    console.print()
    console.print("To resume an existing project:", style="green")
    console.print()
    console.print("  agentic-dev resume --name <project>", style="bold cyan")
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


def _check_prerequisites(language):
    """Check all prerequisites (GitHub user, core tools, auth, language tools). Returns gh_user or None."""
    result = run_cmd(["gh", "api", "user", "--jq", ".login"], capture=True)
    gh_user = result.stdout.strip() if result.returncode == 0 else ""
    if not gh_user:
        console.print("ERROR: Could not determine GitHub username.", style="bold red")
        console.print("Run: gh auth login", style="yellow")
        return None

    for tool, install_mac, install_win in [
        ("git", "brew install git", "winget install Git.Git"),
        ("gh", "brew install gh", "winget install GitHub.cli"),
        ("copilot", None, None),
    ]:
        if not check_command(tool):
            console.print(f"ERROR: {tool} is not installed.", style="bold red")
            install = install_mac if is_macos() else install_win
            if install:
                console.print(f"Run: {install}", style="yellow")
            console.print("Then close and reopen your terminal.", style="yellow")
            return None
        console.print(f"✓ {tool:<8} - OK", style="green")

    auth_result = run_cmd(["gh", "auth", "status"], quiet=True)
    if auth_result.returncode != 0:
        console.print("ERROR: GitHub CLI is not authenticated.", style="bold red")
        console.print("Run: gh auth login", style="yellow")
        return None
    console.print("✓ gh auth  - OK (authenticated)", style="green")

    lang_config = LANGUAGE_CONFIGS[language]
    for prereq in lang_config["prerequisites"]:
        if not check_command(prereq["command"]):
            console.print(f"ERROR: {prereq['error']}", style="bold red")
            install = prereq["install_mac"] if is_macos() else prereq["install_win"]
            console.print(f"Run: {install}", style="yellow")
            console.print("Then close and reopen your terminal.", style="yellow")
            return None
        console.print(f"✓ {prereq['command']:<8} - OK", style="green")

    return gh_user


def _scaffold_project(name, description, gh_user, language):
    """Create repo, write REQUIREMENTS.md, run Copilot bootstrap, clone reviewer/tester. Returns True on success."""
    repo_check = run_cmd(["gh", "repo", "view", f"{gh_user}/{name}"], quiet=True)
    if repo_check.returncode == 0:
        console.print(f"ERROR: Repository {gh_user}/{name} already exists on GitHub.", style="bold red")
        console.print(
            f"Delete it first (gh repo delete {gh_user}/{name}) or choose a different name.",
            style="yellow",
        )
        return False

    parent_dir = os.path.join(os.getcwd(), name)
    os.makedirs(parent_dir, exist_ok=True)
    os.chdir(parent_dir)

    builder_dir = os.path.join(os.getcwd(), "builder")
    os.makedirs(builder_dir, exist_ok=True)
    req_path = os.path.join(builder_dir, "REQUIREMENTS.md")
    with open(req_path, "w", encoding="utf-8") as f:
        f.write("# Original Requirements\n\n")
        f.write("> This document contains the original project requirements as provided by the user.\n")
        f.write("> It must not be modified. All agents should reference this as the ultimate source of truth.\n\n")
        f.write(description)
        f.write("\n")
    console.print("✓ Saved original requirements to REQUIREMENTS.md", style="green")

    prompt = BOOTSTRAP_PROMPT.format(description=description, gh_user=gh_user, name=name)
    exit_code = run_copilot("bootstrap", prompt)

    if exit_code != 0:
        log("bootstrap", "")
        log("bootstrap", "======================================", style="bold red")
        log("bootstrap", " Bootstrap failed! Check errors above", style="bold red")
        log("bootstrap", "======================================", style="bold red")
        return False

    log("bootstrap", "")
    log("bootstrap", "Cloning reviewer copy...", style="cyan")
    run_cmd(["git", "clone", f"https://github.com/{gh_user}/{name}", "reviewer"])

    log("bootstrap", "Cloning tester copy...", style="cyan")
    run_cmd(["git", "clone", f"https://github.com/{gh_user}/{name}", "tester"])

    log("bootstrap", "")
    log("bootstrap", "======================================", style="bold green")
    log("bootstrap", " Bootstrap complete!", style="bold green")
    log("bootstrap", "======================================", style="bold green")
    return True


def run_bootstrap(
    name: str,
    description: str = None,
    language: str = "node",
    spec_file: str = None,
    local: bool = False,
):
    """Internal: scaffold a new project — git repo, GitHub remote (or local bare repo), clone reviewer/tester copies."""
    description = _resolve_description(description, spec_file)

    if language not in VALID_LANGUAGES:
        console.print(
            f"ERROR: Invalid language '{language}'. Choose from: {', '.join(VALID_LANGUAGES)}",
            style="bold red",
        )
        raise typer.Exit(1)

    current_dir = os.path.basename(os.getcwd())
    if current_dir == "multi-agent-dev":
        console.print()
        console.print("WARNING: You are in the multi-agent-dev directory.", style="yellow")
        console.print("Projects will be created as subdirectories here:", style="yellow")
        console.print(f"  {os.getcwd()}/{name}/", style="cyan")
        console.print()
        response = typer.prompt("Are you sure you want to continue? (y/N)")
        if not response.strip().lower().startswith("y"):
            console.print("Bootstrap cancelled.", style="yellow")
            return

    gh_user = _check_prerequisites(language, local=local)
    if not gh_user:
        return

    lang_config = LANGUAGE_CONFIGS[language]
    mode_label = " (local mode)" if local else ""
    console.print()
    console.print(f"Bootstrapping {name} ({lang_config['label']}){mode_label}...", style="cyan")
    console.print()

    if not _scaffold_project(name, description, gh_user, language, local=local):
        return
