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
    REVIEWER_COMMIT_PROMPT,
    REVIEWER_PROMPT,
    TESTER_PROMPT,
)
from agent.utils import (
    check_command,
    clear_builder_done,
    console,
    has_unchecked_items,
    is_builder_done,
    is_macos,
    is_windows,
    log,
    pushd,
    run_cmd,
    run_copilot,
    write_builder_done,
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


@app.command(hidden=True, deprecated=True)
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


def _bootstrap(
    name: str,
    description: str = None,
    language: str = "node",
    spec_file: str = None,
):
    """Internal: scaffold a new project — git repo, GitHub remote, clone reviewer/tester copies."""
    # Resolve description from --spec-file or --description
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

    # Save the original requirements so agents can reference them
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
        write_builder_done()
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
            write_builder_done()
            return

        log("builder", "")
        log("builder", "======================================", style="bold cyan")
        log("builder", " Builder session complete!", style="bold cyan")
        log("builder", "======================================", style="bold cyan")

        if not loop:
            write_builder_done()
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
                write_builder_done()
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


@app.command()
def commitwatch(
    reviewer_dir: Annotated[
        str, typer.Option(help="Path to the reviewer git clone")
    ] = "",
):
    """Watch for new commits and spawn a per-commit code reviewer.

    Runs from the reviewer clone directory. For each new commit detected,
    invokes a reviewer agent scoped to exactly that commit's diff.
    Shuts down automatically when the builder finishes.
    """
    from datetime import datetime

    if reviewer_dir:
        os.chdir(reviewer_dir)

    log("commit-watcher", "======================================", style="bold yellow")
    log("commit-watcher", " Commit watcher started", style="bold yellow")
    log("commit-watcher", " Spawns a reviewer per commit", style="bold yellow")
    log("commit-watcher", " Press Ctrl+C to stop", style="bold yellow")
    log("commit-watcher", "======================================", style="bold yellow")
    log("commit-watcher", "")

    last_sha = ""

    while True:
        # Check if the builder has finished
        if is_builder_done():
            now = datetime.now().strftime("%H:%M:%S")
            log("commit-watcher", "")
            log("commit-watcher", f"[{now}] Builder finished. Shutting down.", style="bold green")
            break

        # Pull latest
        pull_result = run_cmd(["git", "pull", "-q"], capture=True)
        if pull_result.returncode != 0:
            now = datetime.now().strftime("%H:%M:%S")
            log("commit-watcher", f"[{now}] WARNING: git pull failed", style="red")
            if pull_result.stderr:
                log("commit-watcher", pull_result.stderr.strip(), style="red")

        # Get current HEAD
        head_result = run_cmd(["git", "rev-parse", "HEAD"], capture=True)
        current_head = head_result.stdout.strip() if head_result.returncode == 0 else ""

        if current_head and current_head != last_sha and last_sha != "":
            # Enumerate every new commit since our last checkpoint
            log_result = run_cmd(
                ["git", "log", f"{last_sha}..{current_head}", "--format=%H", "--reverse"],
                capture=True,
            )
            new_commits = [
                sha.strip()
                for sha in log_result.stdout.strip().split("\n")
                if sha.strip()
            ]

            now = datetime.now().strftime("%H:%M:%S")
            log("commit-watcher", "")
            log(
                "commit-watcher",
                f"[{now}] {len(new_commits)} new commit(s) detected",
                style="yellow",
            )

            # Review each commit individually
            prev = last_sha
            for commit_sha in new_commits:
                now = datetime.now().strftime("%H:%M:%S")
                short = commit_sha[:8]
                log("commit-watcher", f"[{now}] Reviewing commit {short}...", style="cyan")

                prompt = REVIEWER_COMMIT_PROMPT.format(
                    prev_sha=prev, commit_sha=commit_sha
                )
                exit_code = run_copilot("reviewer", prompt)

                if exit_code != 0:
                    now = datetime.now().strftime("%H:%M:%S")
                    log(
                        "commit-watcher",
                        f"[{now}] WARNING: Review of {short} exited with errors",
                        style="red",
                    )

                prev = commit_sha

                # Check again between commits in case builder finished
                if is_builder_done():
                    now = datetime.now().strftime("%H:%M:%S")
                    log("commit-watcher", f"[{now}] Builder finished. Stopping.", style="bold green")
                    return

            now = datetime.now().strftime("%H:%M:%S")
            log("commit-watcher", f"[{now}] All commits reviewed. Watching...", style="yellow")

        last_sha = current_head if current_head else last_sha
        time.sleep(10)


@app.command()
def testloop(
    interval: Annotated[
        int, typer.Option(help="Minutes between test runs")
    ] = 5,
    tester_dir: Annotated[
        str, typer.Option(help="Path to the tester git clone")
    ] = "",
):
    """Run tests on a timer against the full repo.

    Pulls latest, builds, runs all tests every N minutes.
    Shuts down automatically when the builder finishes.
    """
    from datetime import datetime

    if tester_dir:
        os.chdir(tester_dir)

    log("tester", "======================================", style="bold yellow")
    log("tester", f" Tester running every {interval} minutes", style="bold yellow")
    log("tester", " Press Ctrl+C to stop", style="bold yellow")
    log("tester", "======================================", style="bold yellow")
    log("tester", "")

    interval_seconds = interval * 60

    while True:
        # Check if the builder has finished
        builder_done = is_builder_done()

        now = datetime.now().strftime("%H:%M:%S")
        if builder_done:
            log("tester", f"[{now}] Builder finished. Running final test pass...", style="bold green")
        else:
            log("tester", f"[{now}] Starting test run...", style="cyan")

        # Pull and test
        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)
        exit_code = run_copilot("tester", TESTER_PROMPT)

        now = datetime.now().strftime("%H:%M:%S")
        if exit_code != 0:
            log("tester", f"[{now}] WARNING: Test run exited with errors", style="red")
        else:
            log("tester", f"[{now}] Test run complete.", style="yellow")

        if builder_done:
            log("tester", "")
            log("tester", f"[{now}] Builder finished. Shutting down.", style="bold green")
            break

        log("tester", f"[{now}] Next run in {interval} minutes. Watching...", style="yellow")
        log("tester", "")

        # Sleep in small increments so we can detect builder shutdown sooner
        for _ in range(interval_seconds // 10):
            time.sleep(10)
            if is_builder_done():
                # Builder finished while we were waiting — do one more run
                now = datetime.now().strftime("%H:%M:%S")
                log("tester", f"[{now}] Builder finished. Running final test pass...", style="bold green")
                run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)
                run_copilot("tester", TESTER_PROMPT)
                now = datetime.now().strftime("%H:%M:%S")
                log("tester", f"[{now}] Final test pass complete. Shutting down.", style="bold green")
                return


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
    description: Annotated[str, typer.Option(help="What the project should do")] = None,
    language: Annotated[str, typer.Option(help="Language/stack: dotnet, python, node")] = "node",
    numtasks: Annotated[int, typer.Option(help="Max items per build cycle")] = 5,
    spec_file: Annotated[str, typer.Option(help="Path to a markdown file containing the project requirements")] = None,
):
    """One command to rule them all: bootstrap, plan, and launch all agents."""
    start_dir = os.getcwd()

    _bootstrap(name=name, description=description, language=language, spec_file=spec_file)
    if not os.path.exists(os.path.join(os.getcwd(), "builder")):
        log("orchestrator", "ERROR: Bootstrap did not create the expected directory structure.", style="bold red")
        os.chdir(start_dir)
        return

    parent_dir = os.getcwd()

    os.chdir(os.path.join(parent_dir, "builder"))

    # Clear any stale builder-done sentinel from previous runs
    clear_builder_done()

    log("orchestrator", "")
    log("orchestrator", "======================================", style="bold magenta")
    log("orchestrator", " Running planner...", style="bold magenta")
    log("orchestrator", "======================================", style="bold magenta")
    plan()

    log("orchestrator", "")
    log("orchestrator", "Launching commit watcher (per-commit reviewer)...", style="yellow")
    _spawn_agent_in_terminal(os.path.join(parent_dir, "reviewer"), "commitwatch")

    log("orchestrator", "Launching tester (5-minute timer)...", style="yellow")
    _spawn_agent_in_terminal(os.path.join(parent_dir, "tester"), "testloop")

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

    # Clear any stale builder-done sentinel from previous runs
    clear_builder_done()

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
    log("orchestrator", "Launching commit watcher (per-commit reviewer)...", style="yellow")
    _spawn_agent_in_terminal(reviewer_dir, "commitwatch")

    log("orchestrator", "Launching tester (5-minute timer)...", style="yellow")
    _spawn_agent_in_terminal(tester_dir, "testloop")

    log("orchestrator", "")
    log("orchestrator", "======================================", style="bold green")
    log("orchestrator", " All agents launched! Resuming build...", style="bold green")
    log("orchestrator", "======================================", style="bold green")
    log("orchestrator", "")
    build(numtasks=numtasks, loop=True)

    os.chdir(start_dir)
