"""CLI commands for the multi-agent development orchestrator."""

import os
import subprocess
import sys
import tempfile
import time
from typing import Annotated

import typer

from agent.config import LANGUAGE_CONFIGS, VALID_LANGUAGES
from agent.prompts import (
    BOOTSTRAP_PROMPT,
    BUILDER_PROMPT,
    PLANNER_PROMPT,
    REVIEWER_PROMPT,
    TESTER_PROMPT,
)
from agent.utils import (
    check_command,
    console,
    has_unchecked_items,
    is_macos,
    is_windows,
    log,
    pushd,
    run_cmd,
    run_copilot,
)

app = typer.Typer(
    help="Multi-agent autonomous development orchestrator using GitHub Copilot CLI.",
    no_args_is_help=True,
)


# ============================================
# Commands
# ============================================


@app.command()
def status():
    """Quick view of where things stand — shows SPEC, TASKS, REVIEWS, BUGS."""
    import re

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


@app.command()
def bootstrap(
    name: Annotated[str, typer.Option(help="Project name (used for directory and GitHub repo)")],
    description: Annotated[str, typer.Option(help="What the project should do")],
    language: Annotated[str, typer.Option(help="Language/stack: dotnet, python, node")],
):
    """Create a new project: scaffold, git repo, GitHub remote, clone reviewer/tester copies."""
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

    result = run_cmd(["gh", "api", "user", "--jq", ".login"], capture=True)
    gh_user = result.stdout.strip() if result.returncode == 0 else ""
    if not gh_user:
        console.print("ERROR: Could not determine GitHub username.", style="bold red")
        console.print("Run: gh auth login", style="yellow")
        return

    lang_config = LANGUAGE_CONFIGS[language]

    prereqs_ok = True
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
            prereqs_ok = False
            break
        console.print(f"✓ {tool:<8} - OK", style="green")

    if not prereqs_ok:
        return

    auth_result = run_cmd(["gh", "auth", "status"], quiet=True)
    if auth_result.returncode != 0:
        console.print("ERROR: GitHub CLI is not authenticated.", style="bold red")
        console.print("Run: gh auth login", style="yellow")
        return
    console.print("✓ gh auth  - OK (authenticated)", style="green")

    for prereq in lang_config["prerequisites"]:
        if not check_command(prereq["command"]):
            console.print(f"ERROR: {prereq['error']}", style="bold red")
            install = prereq["install_mac"] if is_macos() else prereq["install_win"]
            console.print(f"Run: {install}", style="yellow")
            console.print("Then close and reopen your terminal.", style="yellow")
            return
        console.print(f"✓ {prereq['command']:<8} - OK", style="green")

    console.print()
    console.print(f"Bootstrapping {name} ({lang_config['label']})...", style="cyan")
    console.print()

    repo_check = run_cmd(["gh", "repo", "view", f"{gh_user}/{name}"], quiet=True)
    if repo_check.returncode == 0:
        console.print(f"ERROR: Repository {gh_user}/{name} already exists on GitHub.", style="bold red")
        console.print(
            f"Delete it first (gh repo delete {gh_user}/{name}) or choose a different name.",
            style="yellow",
        )
        return

    parent_dir = os.path.join(os.getcwd(), name)
    os.makedirs(parent_dir, exist_ok=True)
    os.chdir(parent_dir)

    prompt = BOOTSTRAP_PROMPT.format(description=description, gh_user=gh_user, name=name)
    exit_code = run_copilot("bootstrap", prompt)

    if exit_code != 0:
        log("bootstrap", "")
        log("bootstrap", "======================================", style="bold red")
        log("bootstrap", " Bootstrap failed! Check errors above", style="bold red")
        log("bootstrap", "======================================", style="bold red")
        return

    log("bootstrap", "")
    log("bootstrap", "Cloning reviewer copy...", style="cyan")
    run_cmd(["git", "clone", f"https://github.com/{gh_user}/{name}", "reviewer"])

    log("bootstrap", "Cloning tester copy...", style="cyan")
    run_cmd(["git", "clone", f"https://github.com/{gh_user}/{name}", "tester"])

    log("bootstrap", "")
    log("bootstrap", "======================================", style="bold green")
    log("bootstrap", " Bootstrap complete!", style="bold green")
    log("bootstrap", "======================================", style="bold green")


@app.command()
def build(
    numtasks: Annotated[int, typer.Option(help="Max items (bugs+reviews+tasks) per cycle")] = 5,
    loop: Annotated[bool, typer.Option(help="Run continuously until all work is done")] = False,
):
    """Fix bugs, address reviews, then do tasks. Optionally loop until done."""
    if not os.path.exists("TASKS.md"):
        log("builder", "No TASKS.md found. Run 'plan' first to generate tasks.", style="yellow")
        return

    cycle_count = 0
    no_work_count = 0

    while True:
        cycle_count += 1

        if loop and cycle_count > 1 and (cycle_count % 3) == 1:
            log("builder", "")
            log("builder", f"[Planner] Re-evaluating task plan (cycle {cycle_count})...", style="magenta")
            plan()

        log("builder", "")
        log("builder", f"[Builder] Starting work (up to {numtasks} items)...", style="green")
        log("builder", "")

        prompt = BUILDER_PROMPT.format(numtasks=numtasks)
        exit_code = run_copilot("builder", prompt)

        if exit_code != 0:
            log("builder", "")
            log("builder", "======================================", style="bold red")
            log("builder", " Builder failed! Check errors above", style="bold red")
            log("builder", "======================================", style="bold red")
            return

        log("builder", "")
        log("builder", "======================================", style="bold cyan")
        log("builder", " Builder session complete!", style="bold cyan")
        log("builder", "======================================", style="bold cyan")

        if not loop:
            break

        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

        remaining_bugs = has_unchecked_items("BUGS.md")
        remaining_reviews = has_unchecked_items("REVIEWS.md")
        remaining_tasks = has_unchecked_items("TASKS.md")

        if not remaining_bugs and not remaining_reviews and not remaining_tasks:
            no_work_count += 1

            if no_work_count >= 3:
                log("builder", "")
                log("builder", "======================================", style="bold green")
                log("builder", " All work complete!", style="bold green")
                log("builder", " - Bugs: Done", style="bold green")
                log("builder", " - Reviews: Done", style="bold green")
                log("builder", " - Tasks: Done", style="bold green")
                log("builder", "======================================", style="bold green")
                break
            else:
                log("builder", "")
                log("builder", f"No work found (check {no_work_count}/3)", style="yellow")
                log("builder", "Waiting 1 minute in case reviewer/tester are working...", style="yellow")
                log("builder", "(Ctrl+C to stop)", style="dim")
                time.sleep(60)
                continue

        no_work_count = 0

        log("builder", "")
        log("builder", "Work remaining:", style="cyan")
        if remaining_bugs:
            log("builder", f" - Bugs: {remaining_bugs} unchecked", style="yellow")
        if remaining_reviews:
            log("builder", f" - Reviews: {remaining_reviews} unchecked", style="yellow")
        if remaining_tasks:
            log("builder", f" - Tasks: {remaining_tasks} unchecked", style="yellow")
        log("builder", " Starting next cycle in 5 seconds... (Ctrl+C to stop)", style="cyan")
        time.sleep(5)


def _watch_loop(agent_name: str, prompt: str, label: str) -> None:
    """Shared polling loop for reviewoncommit and testoncommit."""
    from datetime import datetime

    log(agent_name, "======================================", style="bold yellow")
    log(agent_name, f" {label} agent watching for commits...", style="bold yellow")
    log(agent_name, " Press Ctrl+C to stop", style="bold yellow")
    log(agent_name, "======================================", style="bold yellow")
    log(agent_name, "")

    last_commit = ""

    while True:
        pull_result = run_cmd(["git", "pull", "-q"], capture=True)
        if pull_result.returncode != 0:
            now = datetime.now().strftime("%H:%M:%S")
            log(agent_name, f"[{now}] WARNING: git pull failed", style="red")
            if pull_result.stderr:
                log(agent_name, pull_result.stderr.strip(), style="red")

        head_result = run_cmd(["git", "rev-parse", "HEAD"], capture=True)
        current_commit = head_result.stdout.strip() if head_result.returncode == 0 else ""

        if current_commit != last_commit and last_commit != "":
            now = datetime.now().strftime("%H:%M:%S")
            log(agent_name, "")
            log(agent_name, f"[{now}] New commit detected!", style="yellow")
            log(agent_name, "")

            exit_code = run_copilot(agent_name, prompt)

            if exit_code != 0:
                now = datetime.now().strftime("%H:%M:%S")
                log(agent_name, f"[{now}] WARNING: {label} exited with errors", style="red")

            now = datetime.now().strftime("%H:%M:%S")
            log(agent_name, "")
            log(agent_name, f"[{now}] {label} complete. Watching...", style="yellow")

        last_commit = current_commit
        time.sleep(10)


@app.command()
def reviewoncommit():
    """Watch for new commits and review code quality (runs in a loop)."""
    _watch_loop("reviewer", REVIEWER_PROMPT, "Review")


@app.command()
def testoncommit():
    """Watch for new commits and auto-test (runs in a loop)."""
    _watch_loop("tester", TESTER_PROMPT, "Test run")


def _spawn_agent_in_terminal(working_dir: str, command: str) -> None:
    """Launch an agent command in a new terminal window."""
    if is_macos():
        fd, temp_script = tempfile.mkstemp(suffix=".sh")
        with os.fdopen(fd, "w") as f:
            f.write("#!/bin/bash\n")
            f.write(f"cd '{working_dir}'\n")
            f.write(f"agentic-dev {command}\n")
        os.chmod(temp_script, 0o755)
        subprocess.run(
            ["osascript", "-e", f'tell application "Terminal" to do script "{temp_script}"'],
            stdout=subprocess.DEVNULL,
        )
    elif is_windows():
        subprocess.Popen(
            ["agentic-dev", command],
            cwd=working_dir,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    else:
        fd, temp_script = tempfile.mkstemp(suffix=".sh")
        with os.fdopen(fd, "w") as f:
            f.write("#!/bin/bash\n")
            f.write(f"cd '{working_dir}'\n")
            f.write(f"agentic-dev {command}\n")
            f.write("exec bash\n")
        os.chmod(temp_script, 0o755)

        if check_command("gnome-terminal"):
            subprocess.Popen(["gnome-terminal", "--", "bash", temp_script])
        elif check_command("xterm"):
            subprocess.Popen(["xterm", "-e", f"bash {temp_script}"])
        else:
            console.print(
                f"WARNING: Could not find a terminal emulator. "
                f"Please run manually in a new terminal:\n"
                f"  cd {working_dir} && agentic-dev {command}",
                style="yellow",
            )


@app.command()
def go(
    name: Annotated[str, typer.Option(help="Project name")],
    description: Annotated[str, typer.Option(help="What the project should do")],
    language: Annotated[str, typer.Option(help="Language/stack: dotnet, python, node")],
    numtasks: Annotated[int, typer.Option(help="Max items per build cycle")] = 5,
):
    """One command to rule them all: bootstrap, plan, and launch all agents."""
    start_dir = os.getcwd()

    bootstrap(name=name, description=description, language=language)
    if not os.path.exists(os.path.join(os.getcwd(), "builder")):
        log("orchestrator", "ERROR: Bootstrap did not create the expected directory structure.", style="bold red")
        os.chdir(start_dir)
        return

    parent_dir = os.getcwd()

    os.chdir(os.path.join(parent_dir, "builder"))
    log("orchestrator", "")
    log("orchestrator", "======================================", style="bold magenta")
    log("orchestrator", " Running planner...", style="bold magenta")
    log("orchestrator", "======================================", style="bold magenta")
    plan()

    log("orchestrator", "")
    log("orchestrator", "Launching reviewer agent...", style="yellow")
    _spawn_agent_in_terminal(os.path.join(parent_dir, "reviewer"), "reviewoncommit")

    log("orchestrator", "Launching tester agent...", style="yellow")
    _spawn_agent_in_terminal(os.path.join(parent_dir, "tester"), "testoncommit")

    log("orchestrator", "")
    log("orchestrator", "======================================", style="bold green")
    log("orchestrator", " All agents launched! Building...", style="bold green")
    log("orchestrator", "======================================", style="bold green")
    log("orchestrator", "")
    build(numtasks=numtasks, loop=True)

    os.chdir(start_dir)


@app.command()
def resume(
    name: Annotated[str, typer.Option(help="Project name (existing project directory)")],
    numtasks: Annotated[int, typer.Option(help="Max items per build cycle")] = 5,
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
    log("orchestrator", "")
    log("orchestrator", "======================================", style="bold magenta")
    log("orchestrator", " Re-evaluating plan...", style="bold magenta")
    log("orchestrator", "======================================", style="bold magenta")
    plan()

    reviewer_dir = os.path.join(parent_dir, "reviewer")
    tester_dir = os.path.join(parent_dir, "tester")
    with pushd(reviewer_dir):
        run_cmd(["git", "pull", "--rebase"], quiet=True)
    with pushd(tester_dir):
        run_cmd(["git", "pull", "--rebase"], quiet=True)

    log("orchestrator", "")
    log("orchestrator", "Launching reviewer agent...", style="yellow")
    _spawn_agent_in_terminal(reviewer_dir, "reviewoncommit")

    log("orchestrator", "Launching tester agent...", style="yellow")
    _spawn_agent_in_terminal(tester_dir, "testoncommit")

    log("orchestrator", "")
    log("orchestrator", "======================================", style="bold green")
    log("orchestrator", " All agents launched! Resuming build...", style="bold green")
    log("orchestrator", "======================================", style="bold green")
    log("orchestrator", "")
    build(numtasks=numtasks, loop=True)

    os.chdir(start_dir)
