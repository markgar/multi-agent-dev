"""Orchestrator: the 'go' command that detects, bootstraps, and coordinates all agents."""

import os
import re
import shutil
import time
from datetime import datetime, timezone
from typing import Annotated

import typer

from agentic_dev.bootstrap import run_bootstrap, write_workspace_readme
from agentic_dev.planner import check_milestone_sizes, plan
from agentic_dev.prompts import (
    COPILOT_INSTRUCTIONS_PROMPT,
    COPILOT_INSTRUCTIONS_TEMPLATE,
)
from agentic_dev.sentinel import clear_builder_done, is_builder_done
from agentic_dev.terminal import spawn_agent_in_terminal
from agentic_dev.utils import console, ensure_bug_label_exists, ensure_review_labels_exist, log, pushd, run_cmd, run_copilot, validate_model


# Per-agent model map. Keys are agent roles, values are Copilot CLI model names.
# A value of "" means "use the default --model".
AgentModels = dict[str, str]

_AGENT_ROLES = ("builder", "reviewer", "milestone_reviewer", "tester", "validator", "planner", "backlog")


def resolve_agent_models(
    default_model: str,
    builder_model: str | None = None,
    reviewer_model: str | None = None,
    milestone_reviewer_model: str | None = None,
    tester_model: str | None = None,
    validator_model: str | None = None,
    planner_model: str | None = None,
    backlog_model: str | None = None,
) -> AgentModels:
    """Build the per-agent model dict, validating overrides and falling back
    to *default_model* for any role without an explicit override.

    Pure function: validates each override via validate_model() and returns a
    dict mapping role names to Copilot CLI model identifiers.

    The 'backlog' role is special: it only applies to the initial backlog
    creation prompt (PLANNER_INITIAL_PROMPT). All other planner passes
    (completeness, quality, ordering, milestone planning) use the 'planner'
    model. When backlog_model is not set, it falls back to the planner model.
    """
    overrides = {
        "builder": builder_model,
        "reviewer": reviewer_model,
        "milestone_reviewer": milestone_reviewer_model,
        "tester": tester_model,
        "validator": validator_model,
        "planner": planner_model,
    }
    result: AgentModels = {}
    for role, override in overrides.items():
        if override:
            result[role] = validate_model(override)
        else:
            result[role] = default_model
    # Backlog model falls back to planner model, not default_model
    if backlog_model:
        result["backlog"] = validate_model(backlog_model)
    else:
        result["backlog"] = result["planner"]
    return result

def register(app: typer.Typer) -> None:
    """Register orchestrator commands on the shared app."""
    app.command()(go)


# ============================================
# Clone and repo detection helpers
# ============================================


def _detect_clone_source(parent_dir: str) -> str:
    """Determine the git clone source for creating missing agent clones.

    Reads the remote URL from the first builder clone found (builder-1/ or
    legacy builder/). Returns empty string if neither is found.
    """
    # Check numbered builders first, then legacy builder/
    for candidate in ("builder-1", "builder"):
        candidate_dir = os.path.join(parent_dir, candidate)
        if os.path.exists(candidate_dir):
            with pushd(candidate_dir):
                result = run_cmd(["git", "remote", "get-url", "origin"], capture=True)
            if result.returncode == 0:
                return result.stdout.strip()
    return ""


def _find_existing_repo(parent_dir: str, name: str, org: str = "") -> str:
    """Check if the project repo already exists. Returns the clone URL/path, or empty string.

    Checks for the repo on GitHub via gh repo view.
    When org is provided, checks under the org instead of the authenticated user.
    """
    if org:
        owner = org
    else:
        result = run_cmd(["gh", "api", "user", "--jq", ".login"], capture=True)
        owner = result.stdout.strip() if result.returncode == 0 else ""
    if not owner:
        return ""
    repo_check = run_cmd(["gh", "repo", "view", f"{owner}/{name}"], quiet=True)
    if repo_check.returncode == 0:
        return f"https://github.com/{owner}/{name}"
    return ""


def _clone_all_agents(parent_dir: str, clone_source: str, num_builders: int = 1) -> None:
    """Clone any missing agent directories from the given source."""
    os.makedirs(parent_dir, exist_ok=True)
    agents = (
        [f"builder-{i}" for i in range(1, num_builders + 1)]
        + [f"reviewer-{i}" for i in range(1, num_builders + 1)]
        + ["milestone-reviewer", "tester", "validator"]
    )
    for agent in agents:
        agent_dir = os.path.join(parent_dir, agent)
        if not os.path.exists(agent_dir):
            log("orchestrator", f"Cloning {agent} from existing repo...", style="cyan")
            with pushd(parent_dir):
                run_cmd(["git", "clone", clone_source, agent])
    write_workspace_readme(parent_dir)


def _pull_all_clones(parent_dir: str, num_builders: int = 1) -> None:
    """Pull latest on all agent clones. Create any missing clones."""
    clone_source = _detect_clone_source(parent_dir)

    agents = (
        [f"builder-{i}" for i in range(1, num_builders + 1)]
        + [f"reviewer-{i}" for i in range(1, num_builders + 1)]
        + ["milestone-reviewer", "tester", "validator"]
    )
    for agent in agents:
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


def _migrate_legacy_builder(parent_dir: str) -> None:
    """Rename legacy builder/ to builder-1/ if needed.

    Handles the migration from old single-builder layout to numbered builders.
    """
    builder_old = os.path.join(parent_dir, "builder")
    builder_new = os.path.join(parent_dir, "builder-1")
    if os.path.exists(builder_old) and not os.path.exists(builder_new):
        try:
            shutil.move(builder_old, builder_new)
        except OSError as exc:
            log("orchestrator", f"Failed to migrate builder/ to builder-1/: {exc}", style="yellow")
            return
        log("orchestrator", "Migrated builder/ to builder-1/", style="cyan")


def _migrate_legacy_reviewer(parent_dir: str) -> None:
    """Rename legacy reviewer/ to reviewer-1/ if needed.

    Handles the migration from single-reviewer layout to per-builder reviewers.
    """
    reviewer_old = os.path.join(parent_dir, "reviewer")
    reviewer_new = os.path.join(parent_dir, "reviewer-1")
    if os.path.exists(reviewer_old) and not os.path.exists(reviewer_new):
        try:
            shutil.move(reviewer_old, reviewer_new)
        except OSError as exc:
            log("orchestrator", f"Failed to migrate reviewer/ to reviewer-1/: {exc}", style="yellow")
            return
        log("orchestrator", "Migrated reviewer/ to reviewer-1/", style="cyan")


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


def _generate_copilot_instructions(model: str = "") -> None:
    """Generate .github/copilot-instructions.md from SPEC.md and milestones/."""
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
    exit_code = run_copilot("orchestrator", prompt, model=model)

    if exit_code == 0:
        log("orchestrator", "copilot-instructions.md generated.", style="green")
    else:
        log("orchestrator", "WARNING: Failed to generate copilot-instructions.md. Continuing.", style="yellow")


# ============================================
# Agent launching and build orchestration
# ============================================


def _launch_agents_and_build(
    parent_dir: str, plan_label: str, project_name: str = "",
    requirements_changed: bool = False, num_builders: int = 1,
    agent_models: AgentModels | None = None,
) -> None:
    """Run planner, spawn all agents (including builders) in terminals, then poll for completion."""
    if agent_models is None:
        agent_models = {}
    clear_builder_done(num_builders)
    ensure_bug_label_exists()
    ensure_review_labels_exist()

    log("orchestrator", "")
    log("orchestrator", "======================================", style="bold magenta")
    log("orchestrator", f" {plan_label}", style="bold magenta")
    log("orchestrator", "======================================", style="bold magenta")
    plan_ok = plan(
        requirements_changed=requirements_changed,
        model=agent_models.get("planner", ""),
        backlog_model=agent_models.get("backlog", ""),
    )
    if not plan_ok:
        log("orchestrator", "")
        log("orchestrator", "Planner failed — aborting. Fix the issue and re-run.", style="bold red")
        return
    check_milestone_sizes(model=agent_models.get("planner", ""))
    _generate_copilot_instructions(model=agent_models.get("planner", ""))

    # Launch branch-attached reviewers for milestone builders only.
    # The issue builder (last builder when num_builders > 1) doesn't get a reviewer.
    milestone_builder_count = num_builders - 1 if num_builders > 1 else num_builders
    log("orchestrator", "")
    for i in range(1, milestone_builder_count + 1):
        log("orchestrator", f"Launching branch-attached reviewer-{i}...", style="yellow")
        reviewer_dir = os.path.join(parent_dir, f"reviewer-{i}")
        spawn_agent_in_terminal(reviewer_dir, f"commitwatch --builder-id {i}",
                                model=agent_models.get("reviewer", ""))

    log("orchestrator", "Launching milestone reviewer...", style="yellow")
    spawn_agent_in_terminal(os.path.join(parent_dir, "milestone-reviewer"), "milestonewatch",
                            model=agent_models.get("milestone_reviewer", ""))

    log("orchestrator", "Launching tester (milestone-triggered)...", style="yellow")
    spawn_agent_in_terminal(os.path.join(parent_dir, "tester"), "testloop",
                            model=agent_models.get("tester", ""))

    log("orchestrator", "Launching validator (milestone-triggered)...", style="yellow")
    validator_cmd = f"validateloop --project-name {project_name}" if project_name else "validateloop"
    spawn_agent_in_terminal(os.path.join(parent_dir, "validator"), validator_cmd,
                            model=agent_models.get("validator", ""))

    # Spawn builders as terminal processes.
    # Claim races are handled by optimistic locking in the builder
    # (push fails → reset → pull → try next story), so no stagger needed.
    # When num_builders > 1, the last builder is the dedicated issue builder.
    for i in range(1, num_builders + 1):
        builder_dir = os.path.join(parent_dir, f"builder-{i}")
        is_issue_builder = num_builders > 1 and i == num_builders
        role_flag = " --role issue" if is_issue_builder else ""
        builder_cmd = f"build --loop --builder-id {i} --num-builders {num_builders}{role_flag}"
        role_label = "issue builder" if is_issue_builder else f"builder-{i}"
        log("orchestrator", f"Launching {role_label}...", style="yellow")
        spawn_agent_in_terminal(builder_dir, builder_cmd,
                                model=agent_models.get("builder", ""))

    log("orchestrator", "")
    log("orchestrator", "======================================", style="bold green")
    log("orchestrator", " All agents launched!", style="bold green")
    log("orchestrator", "======================================", style="bold green")
    log("orchestrator", "")

    _wait_for_builders()


def _wait_for_builders() -> None:
    """Block until all builders have finished (or stale-log timeout)."""
    while True:
        if is_builder_done():
            log("orchestrator", "")
            log("orchestrator", "======================================", style="bold green")
            log("orchestrator", " All builders done. Run complete.", style="bold green")
            log("orchestrator", "======================================", style="bold green")
            return
        time.sleep(15)


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
    parent_dir: str, project_name: str, description: str, spec_file: str,
    start_dir: str, num_builders: int = 1,
    agent_models: AgentModels | None = None, org: str = "",
) -> None:
    """Bootstrap a brand-new project: create repo, plan, and launch agents."""
    if not description and not spec_file:
        console.print("ERROR: New project requires --description or --spec-file.", style="bold red")
        return

    run_bootstrap(directory=parent_dir, name=project_name, description=description, spec_file=spec_file, org=org)
    if not os.path.exists(os.path.join(parent_dir, "builder")):
        log("orchestrator", "ERROR: Bootstrap did not create the expected directory structure.", style="bold red")
        os.chdir(start_dir)
        return

    # Rename builder/ to builder-1/ for multi-builder consistency
    _migrate_legacy_builder(parent_dir)
    _migrate_legacy_reviewer(parent_dir)

    # Clone additional builders and reviewers if N > 1
    if num_builders > 1:
        clone_source = _detect_clone_source(parent_dir)
        if clone_source:
            for i in range(2, num_builders + 1):
                for role in (f"builder-{i}", f"reviewer-{i}"):
                    role_dir = os.path.join(parent_dir, role)
                    if not os.path.exists(role_dir):
                        log("orchestrator", f"Cloning {role}...", style="cyan")
                        with pushd(parent_dir):
                            run_cmd(["git", "clone", clone_source, role])

    os.chdir(os.path.join(parent_dir, "builder-1"))
    _launch_agents_and_build(
        parent_dir, "Running backlog planner...",
        project_name=project_name, num_builders=num_builders,
        agent_models=agent_models,
    )


def _resume_existing_project(
    parent_dir: str, project_name: str, repo_source: str, description: str, spec_file: str,
    num_builders: int = 1, agent_models: AgentModels | None = None, org: str = "",
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

    # Migrate legacy builder/ and reviewer/ to numbered directories before cloning
    _migrate_legacy_builder(parent_dir)
    _migrate_legacy_reviewer(parent_dir)

    _clone_all_agents(parent_dir, repo_source, num_builders)
    _pull_all_clones(parent_dir, num_builders)
    os.chdir(os.path.join(parent_dir, "builder-1"))

    if new_description:
        _update_requirements(os.path.join(parent_dir, "builder-1"), new_description)

    _launch_agents_and_build(
        parent_dir, "Running milestone planner...",
        project_name=project_name, requirements_changed=bool(new_description),
        num_builders=num_builders, agent_models=agent_models,
    )


def go(
    directory: Annotated[str, typer.Option(help="Project directory path (created if new, resumed if existing)")],
    model: Annotated[str, typer.Option(help="Copilot model to use (required). Allowed: gpt-5.3-codex, claude-opus-4.6, claude-opus-4.6-fast, claude-sonnet-4.6, claude-haiku-4.5")],
    description: Annotated[str, typer.Option(help="What the project should do")] = None,
    spec_file: Annotated[str, typer.Option(help="Path to a markdown file containing the project requirements")] = None,
    name: Annotated[str, typer.Option(help="GitHub repo name (defaults to directory basename)")] = None,
    org: Annotated[str, typer.Option(help="GitHub org to create the repo in (defaults to personal account)")] = None,
    builders: Annotated[int, typer.Option(help="Number of parallel builders (default 1)")] = 1,
    builder_model: Annotated[str, typer.Option(help="Model override for builder agents")] = None,
    reviewer_model: Annotated[str, typer.Option(help="Model override for commit-watcher reviewers")] = None,
    milestone_reviewer_model: Annotated[str, typer.Option(help="Model override for the milestone reviewer")] = None,
    tester_model: Annotated[str, typer.Option(help="Model override for the tester agent")] = None,
    validator_model: Annotated[str, typer.Option(help="Model override for the validator agent")] = None,
    planner_model: Annotated[str, typer.Option(help="Model override for the planner (initial plan + copilot-instructions)")] = None,
    backlog_model: Annotated[str, typer.Option(help="Model override for initial backlog creation only (falls back to --planner-model)")] = None,
) -> None:
    """Start or continue a project. Detects whether the project already exists.

    New project:      bootstraps, plans, and launches all agents.
    Existing project: pulls latest, optionally updates requirements, re-plans, and builds.

    --directory is the project working directory — relative or absolute.
    --name optionally overrides the GitHub repo name (defaults to basename of directory).
    --builders controls how many parallel builder agents are launched (default 1).

    Per-agent model overrides (all optional, default to --model):
      --builder-model, --reviewer-model, --milestone-reviewer-model,
      --tester-model, --validator-model, --planner-model
    """
    default_model = validate_model(model)
    os.environ["COPILOT_MODEL"] = default_model

    agent_models = resolve_agent_models(
        default_model,
        builder_model=builder_model,
        reviewer_model=reviewer_model,
        milestone_reviewer_model=milestone_reviewer_model,
        tester_model=tester_model,
        validator_model=validator_model,
        planner_model=planner_model,
        backlog_model=backlog_model,
    )

    console.print(f"Using model: {default_model}", style="bold green")
    # Show per-agent overrides
    for role in _AGENT_ROLES:
        role_model = agent_models.get(role, default_model)
        if role_model != default_model:
            display_role = role.replace("_", "-")
            console.print(f"  {display_role}: {role_model}", style="green")
    if builders > 1:
        console.print(f"Parallel builders: {builders}", style="bold green")

    start_dir = os.getcwd()

    # --- Resolve project directory ---
    parent_dir = _resolve_directory(directory)
    if parent_dir is None:
        return

    project_name = name or os.path.basename(parent_dir)

    gh_org = org or ""

    # --- Check if the repo already exists (on GitHub) ---
    repo_source = _find_existing_repo(parent_dir, project_name, org=gh_org)

    if not repo_source:
        _bootstrap_new_project(
            parent_dir, project_name, description, spec_file, start_dir,
            num_builders=builders, agent_models=agent_models, org=gh_org,
        )
    else:
        _resume_existing_project(
            parent_dir, project_name, repo_source, description, spec_file,
            num_builders=builders, agent_models=agent_models, org=gh_org,
        )

    os.chdir(start_dir)
