"""Validator command: watch for completed milestones, build containers, and run acceptance tests."""

import glob
import hashlib
import os
import shutil
import time
from datetime import datetime
from typing import Annotated

import typer

from agentic_dev.git_helpers import git_push_with_retry
from agentic_dev.journeys import (
    format_journey_prompt_block,
    select_journeys_for_milestone,
)
from agentic_dev.milestone import (
    load_milestone_boundaries,
    load_reviewed_milestones,
    save_milestone_checkpoint,
)
from agentic_dev.prompts import (
    VALIDATOR_JOURNEY_RESULTS_TAGS,
    VALIDATOR_JOURNEY_SECTION,
    VALIDATOR_LEGACY_RESULTS_TAGS,
    VALIDATOR_LEGACY_SCOPE,
    VALIDATOR_MILESTONE_PROMPT,
    VALIDATOR_PLAYWRIGHT_SECTION,
    VALIDATOR_PLAYWRIGHT_TRACE_SECTION,
)
from agentic_dev.sentinel import is_builder_done
from agentic_dev.utils import log, run_cmd, run_copilot, resolve_logs_dir


_VALIDATOR_MILESTONE_CHECKPOINT = "validator.milestone"

_FRONTEND_EXTENSIONS = ("*.tsx", "*.jsx", "*.vue", "*.svelte")
_FRONTEND_KEYWORDS = (
    "frontend", "react", "vue", "angular", "svelte", "next.js", "nuxt",
    "vite", "webpack", "tailwind", "UI ", "user interface", "single-page",
    "SPA", "pages should render", "web app", "dashboard",
)


def compute_project_ports(project_name: str) -> tuple[int, int]:
    """Compute deterministic host ports from a project name for port isolation.

    Returns (app_port, secondary_port). Maps project name to port range 3000-8999
    so multiple projects can run side-by-side without port conflicts.
    Uses SHA-256 for a stable hash across Python sessions.
    """
    digest = hashlib.sha256(project_name.encode()).hexdigest()
    base = int(digest, 16) % 6000 + 3000
    return base, base + 1


def detect_has_frontend(repo_dir: str) -> bool:
    """Return True if the repo appears to contain a frontend/UI component.

    Checks three signals:
    1. A package.json exists (root or one level deep).
    2. Frontend-framework source files exist (tsx, jsx, vue, svelte).
    3. SPEC.md contains frontend-related keywords.

    Pure-ish function: only reads the filesystem, no side effects.
    """
    # Signal 1: package.json at root or one directory deep
    if os.path.isfile(os.path.join(repo_dir, "package.json")):
        return True
    if glob.glob(os.path.join(repo_dir, "*/package.json")):
        return True

    # Signal 2: frontend framework source files (search up to 4 levels deep)
    for ext in _FRONTEND_EXTENSIONS:
        pattern = os.path.join(repo_dir, "**", ext)
        if glob.glob(pattern, recursive=True):
            return True

    # Signal 3: SPEC.md mentions frontend keywords
    spec_path = os.path.join(repo_dir, "SPEC.md")
    if os.path.isfile(spec_path):
        try:
            content = open(spec_path, encoding="utf-8").read().lower()
            for keyword in _FRONTEND_KEYWORDS:
                if keyword.lower() in content:
                    return True
        except OSError:
            pass

    return False


def find_unvalidated_milestones(boundaries: list[dict], validated: set[str]) -> list[dict]:
    """Return milestone boundaries that have not yet been validated.

    Pure function: filters boundaries by membership in the validated set.
    """
    return [b for b in boundaries if b["name"] not in validated]


def _cleanup_containers() -> None:
    """Stop and remove any containers from previous validator runs.

    Runs docker compose down if a compose file exists. Never raises.
    """
    try:
        for compose_file in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
            if os.path.exists(compose_file):
                run_cmd(["docker", "compose", "down", "--remove-orphans"], quiet=True)
                return
        # Fallback: remove containers with the 'validator' label if any
        ps_result = run_cmd(
            ["docker", "ps", "-aq", "--filter", "label=validator"],
            capture=True,
        )
        container_ids = ps_result.stdout.strip().split() if ps_result.returncode == 0 and ps_result.stdout.strip() else []
        if container_ids:
            run_cmd(["docker", "rm", "-f"] + container_ids, quiet=True)
    except Exception:
        pass


def _commit_uncommitted_changes() -> None:
    """Commit any uncommitted changes left behind by Copilot.

    Safety net: if Copilot made file changes but did not commit them,
    this bundles them into a single commit so they can be cherry-picked.
    Does nothing if the working tree is clean.
    """
    status = run_cmd(["git", "status", "--porcelain"], capture=True)
    if status.returncode != 0 or not status.stdout.strip():
        return
    run_cmd(["git", "add", "-A"], quiet=True)
    run_cmd(
        ["git", "commit", "-m", "[validator] Save uncommitted validation changes"],
        quiet=True,
    )


def _collect_detached_commits(base_sha: str) -> list[str]:
    """Return commit SHAs made since base_sha on the current (detached) HEAD.

    Returns them in chronological order (oldest first) so they can be
    cherry-picked in sequence. Returns an empty list if there are no new commits.
    """
    result = run_cmd(
        ["git", "log", f"{base_sha}..HEAD", "--format=%H", "--reverse"],
        capture=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return [sha.strip() for sha in result.stdout.strip().split("\n") if sha.strip()]


def _cherry_pick_commits(commits: list[str]) -> bool:
    """Cherry-pick a list of commits onto the current branch.

    On conflict, attempts to resolve by accepting the cherry-picked version.
    Returns True if all commits were applied, False if any failed (aborts that pick).
    """
    for sha in commits:
        result = run_cmd(["git", "cherry-pick", "--no-edit", sha], capture=True)
        if result.returncode == 0:
            continue
        # Conflict — try to resolve by adding everything and continuing
        run_cmd(["git", "add", "-A"], quiet=True)
        cont = run_cmd(
            ["git", "-c", "core.editor=true", "cherry-pick", "--continue"],
            capture=True,
        )
        if cont.returncode != 0:
            run_cmd(["git", "cherry-pick", "--abort"], quiet=True)
            log("validator", f"Cherry-pick of {sha[:8]} failed, skipping", style="yellow")
            return False
    return True


def _copy_validation_results(milestone_name: str) -> None:
    """Copy validation-results.txt from the working dir to logs/.

    The validator prompt asks Copilot to write this file but not commit it.
    We copy it to logs/ with the milestone name for post-run analysis.
    Silently does nothing if the file doesn't exist.
    """
    results_file = "validation-results.txt"
    if not os.path.exists(results_file):
        return
    try:
        logs_dir = resolve_logs_dir()
        safe_name = milestone_name.lower().replace(" ", "-")
        dest = os.path.join(logs_dir, f"validation-{safe_name}.txt")
        shutil.copy(results_file, dest)
        log("validator", f"Validation results saved to {dest}", style="blue")
        os.remove(results_file)
    except Exception:
        pass


def _print_validation_summary(milestone_name: str) -> None:
    """Log a pass/fail summary from the validation results file.

    Reads logs/validation-<milestone>.txt, counts PASS/FAIL per category
    tag ([A], [B], [C], [UI], other), and logs a summary table plus up to
    10 individual failure lines. Always called after _copy_validation_results.
    """
    try:
        logs_dir = resolve_logs_dir()
        safe_name = milestone_name.lower().replace(" ", "-")
        results_path = os.path.join(logs_dir, f"validation-{safe_name}.txt")
        if not os.path.exists(results_path):
            log("validator", "No validation results file found — skipping summary", style="yellow")
            return

        lines = open(results_path, encoding="utf-8").read().strip().splitlines()
        if not lines:
            log("validator", "Validation results file is empty", style="yellow")
            return

        categories = {"[A]": "Milestone tests", "[B]": "Requirements coverage",
                      "[C]": "Bug verification", "[UI]": "Playwright UI"}
        counts: dict[str, dict[str, int]] = {}
        for tag in list(categories.keys()) + ["journey", "other"]:
            counts[tag] = {"PASS": 0, "FAIL": 0}

        import re as _re
        _journey_tag_re = _re.compile(r"\[J-\d+\]")

        failures: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            is_pass = stripped.upper().startswith("PASS")
            is_fail = stripped.upper().startswith("FAIL")
            if not is_pass and not is_fail:
                continue
            result_key = "PASS" if is_pass else "FAIL"
            matched_tag = "other"
            if _journey_tag_re.search(stripped):
                matched_tag = "journey"
            else:
                for tag in categories:
                    if tag in stripped:
                        matched_tag = tag
                        break
            counts[matched_tag][result_key] += 1
            if is_fail:
                failures.append(stripped)

        total_pass = sum(c["PASS"] for c in counts.values())
        total_fail = sum(c["FAIL"] for c in counts.values())

        log("validator", f"--- Validation Summary: {milestone_name} ---", style="bold cyan")
        for tag, label in categories.items():
            p, f = counts[tag]["PASS"], counts[tag]["FAIL"]
            if p + f == 0:
                continue
            style = "green" if f == 0 else "red"
            log("validator", f"  {label} {tag}: {p} passed, {f} failed", style=style)

        # Journey results
        jp, jf = counts["journey"]["PASS"], counts["journey"]["FAIL"]
        if jp + jf > 0:
            style = "green" if jf == 0 else "red"
            log("validator", f"  Journey tests [J-*]: {jp} passed, {jf} failed", style=style)

        op, of = counts["other"]["PASS"], counts["other"]["FAIL"]
        if op + of > 0:
            style = "green" if of == 0 else "red"
            log("validator", f"  Other: {op} passed, {of} failed", style=style)

        overall_style = "bold green" if total_fail == 0 else "bold red"
        log("validator", f"  TOTAL: {total_pass} passed, {total_fail} failed", style=overall_style)

        if failures:
            log("validator", "  Failures:", style="red")
            for fail_line in failures[:10]:
                log("validator", f"    {fail_line}", style="red")
            if len(failures) > 10:
                log("validator", f"    ... and {len(failures) - 10} more", style="red")
    except Exception as exc:
        log("validator", f"Could not print validation summary: {exc}", style="yellow")


def _copy_playwright_traces(milestone_name: str) -> None:
    """Copy Playwright HTML report and traces to logs/ for post-run analysis.

    Copies e2e/playwright-report/ → logs/playwright-<milestone>/report/
    and e2e/test-results/ → logs/playwright-<milestone>/traces/.
    Only called when save_traces=True. Silently skips missing source dirs.
    """
    try:
        logs_dir = resolve_logs_dir()
        safe_name = milestone_name.lower().replace(" ", "-")
        dest_base = os.path.join(logs_dir, f"playwright-{safe_name}")

        copied_any = False
        for src_dir, dest_subdir in [
            (os.path.join("e2e", "playwright-report"), "report"),
            (os.path.join("e2e", "test-results"), "traces"),
        ]:
            if os.path.isdir(src_dir):
                dest_dir = os.path.join(dest_base, dest_subdir)
                shutil.copytree(src_dir, dest_dir, dirs_exist_ok=True)
                copied_any = True

        if copied_any:
            log("validator", f"Playwright artifacts saved to {dest_base}", style="blue")
    except Exception as exc:
        log("validator", f"Could not copy Playwright traces: {exc}", style="yellow")


def _read_file_at_sha(path: str) -> str:
    """Read a file's content at the currently checked-out commit.

    Returns the file content as a string, or empty string if the file
    doesn't exist. Used to read JOURNEYS.md and BACKLOG.md at the
    milestone's detached HEAD.
    """
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    except OSError:
        pass
    return ""


def _build_validation_scope(boundary: dict) -> tuple[str, str]:
    """Determine the validation scope for a milestone.

    Reads JOURNEYS.md and BACKLOG.md at the currently checked-out SHA.
    If eligible journeys exist, returns a journey-based scope; otherwise
    falls back to the legacy three-part (A/B/C) scope.

    Returns (validation_scope, results_tag_instructions) — two prompt
    fragments ready for interpolation into VALIDATOR_MILESTONE_PROMPT.
    """
    journeys_content = _read_file_at_sha("JOURNEYS.md")
    backlog_content = _read_file_at_sha("BACKLOG.md")

    selected = []
    if journeys_content and backlog_content:
        selected = select_journeys_for_milestone(journeys_content, backlog_content)

    if selected:
        journey_list = format_journey_prompt_block(selected)
        journey_ids = ", ".join(j.id for j in selected)
        log("validator", f"Journey-based validation: running {journey_ids}", style="cyan")
        scope = VALIDATOR_JOURNEY_SECTION.format(
            journey_list=journey_list, milestone_name=boundary["name"]
        )
        return scope, VALIDATOR_JOURNEY_RESULTS_TAGS

    log("validator", "No eligible journeys found — using legacy A/B/C scope", style="dim")
    scope = VALIDATOR_LEGACY_SCOPE.format(milestone_name=boundary["name"])
    return scope, VALIDATOR_LEGACY_RESULTS_TAGS


def _validate_milestone(boundary: dict, project_name: str, save_traces: bool = False) -> None:
    """Build a container, validate at the milestone's end SHA, and leave running.

    Flow: checkout milestone SHA (detached HEAD) → set COMPOSE_PROJECT_NAME for
    container isolation → read JOURNEYS.md + BACKLOG.md to determine validation
    scope → run Copilot validation → collect any commits Copilot made → return
    to main → cherry-pick commits onto main → push.
    Containers are left running so the app is browsable after validation.
    """
    now = datetime.now().strftime("%H:%M:%S")
    log(
        "validator",
        f"[{now}] Milestone completed: {boundary['name']}! "
        "Building container and validating...",
        style="bold cyan",
    )

    app_port, secondary_port = compute_project_ports(project_name)
    compose_name = project_name.lower().replace(" ", "-")
    os.environ["COMPOSE_PROJECT_NAME"] = compose_name

    run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)
    run_cmd(["git", "checkout", boundary["end_sha"]], quiet=True)
    _cleanup_containers()

    has_frontend = detect_has_frontend(".")
    ui_instructions = VALIDATOR_PLAYWRIGHT_SECTION if has_frontend else ""
    if has_frontend and save_traces:
        ui_instructions += "\n\n" + VALIDATOR_PLAYWRIGHT_TRACE_SECTION

    validation_scope, results_tag_instructions = _build_validation_scope(boundary)

    prompt = VALIDATOR_MILESTONE_PROMPT.format(
        milestone_name=boundary["name"],
        milestone_start_sha=boundary["start_sha"],
        milestone_end_sha=boundary["end_sha"],
        validation_scope=validation_scope,
        results_tag_instructions=results_tag_instructions,
        ui_testing_instructions=ui_instructions,
        compose_project_name=compose_name,
        app_port=app_port,
        secondary_port=secondary_port,
    )
    exit_code = run_copilot("validator", prompt)

    _copy_validation_results(boundary["name"])
    _print_validation_summary(boundary["name"])
    if save_traces:
        _copy_playwright_traces(boundary["name"])
    # Containers are intentionally left running for live browsing.
    # They will be cleaned up at the start of the next milestone's validation.

    # Collect commits Copilot made on detached HEAD
    _commit_uncommitted_changes()
    new_commits = _collect_detached_commits(boundary["end_sha"])

    # Return to main and pull latest before applying validator's work
    run_cmd(["git", "checkout", "main"], quiet=True)
    run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

    if new_commits:
        pick_ok = _cherry_pick_commits(new_commits)
        if pick_ok:
            git_push_with_retry("validator")
        else:
            log(
                "validator",
                "Could not cherry-pick validator commits onto main — "
                "validation results are saved in logs/ but code changes were lost.",
                style="red",
            )

    now = datetime.now().strftime("%H:%M:%S")
    if exit_code != 0:
        log("validator", f"[{now}] WARNING: Validation run exited with errors", style="red")
    else:
        log("validator", f"[{now}] Milestone validated: {boundary['name']}", style="blue")
        log(
            "validator",
            f"  App running at http://localhost:{app_port}",
            style="bold green",
        )

    save_milestone_checkpoint(
        boundary["name"],
        checkpoint_file=_VALIDATOR_MILESTONE_CHECKPOINT,
    )


def register(app: typer.Typer) -> None:
    """Register validator commands on the shared app."""
    app.command()(validateloop)


def validateloop(
    interval: Annotated[
        int, typer.Option(help="Seconds between poll cycles")
    ] = 10,
    validator_dir: Annotated[
        str, typer.Option(help="Path to the validator git clone")
    ] = "",
    project_name: Annotated[
        str, typer.Option(help="Project name for container namespace and port isolation")
    ] = "",
    save_traces: Annotated[
        bool, typer.Option("--save-traces", help="Save Playwright HTML reports and traces to logs/")
    ] = False,
) -> None:
    """Watch for completed milestones, build containers, and run acceptance tests.

    Polls logs/milestones.log for newly completed milestones. When one appears,
    pulls latest code, builds the app in a Docker container, starts it, and
    validates it against SPEC.md acceptance criteria scoped to the current milestone.
    Deployment knowledge is persisted in DEPLOY.md for future runs.
    Containers are left running after successful validation for live browsing.
    """
    if validator_dir:
        os.chdir(validator_dir)

    if not project_name:
        project_name = os.path.basename(os.path.dirname(os.getcwd()))

    app_port, _ = compute_project_ports(project_name)

    log("validator", "======================================", style="bold blue")
    log("validator", " Validator watching for completed milestones", style="bold blue")
    log("validator", f" Project: {project_name} | App port: {app_port}", style="bold blue")
    log("validator", " Press Ctrl+C to stop", style="bold blue")
    log("validator", "======================================", style="bold blue")
    log("validator", "")

    try:
        _validateloop_inner(interval, project_name, save_traces)
    except SystemExit as exc:
        log("validator", f"FATAL: {exc}", style="bold red")
        raise
    except Exception as exc:
        log("validator", f"FATAL: Unexpected error: {exc}", style="bold red")
        raise


def _drain_remaining_milestones(project_name: str, save_traces: bool = False) -> None:
    """Process all remaining milestones after the builder has finished.

    Keeps pulling and validating until no unvalidated milestones remain.
    This ensures milestones completed while the validator was busy are not skipped.
    """
    while True:
        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)
        boundaries = load_milestone_boundaries()
        validated = load_reviewed_milestones(checkpoint_file=_VALIDATOR_MILESTONE_CHECKPOINT)
        remaining = find_unvalidated_milestones(boundaries, validated)
        if not remaining:
            break
        now = datetime.now().strftime("%H:%M:%S")
        log(
            "validator",
            f"[{now}] Draining {len(remaining)} remaining milestone(s)...",
            style="yellow",
        )
        for boundary in remaining:
            _validate_milestone(boundary, project_name, save_traces)


def _validateloop_inner(interval: int, project_name: str, save_traces: bool = False) -> None:
    """Inner loop for validateloop, separated for crash-logging wrapper."""
    while True:
        # Check if the builder has finished
        builder_done = is_builder_done()

        # Pull latest so we see new milestones.log entries
        run_cmd(["git", "pull", "--rebase", "-q"], quiet=True)

        # Check for newly completed milestones
        boundaries = load_milestone_boundaries()
        validated = load_reviewed_milestones(checkpoint_file=_VALIDATOR_MILESTONE_CHECKPOINT)

        for boundary in find_unvalidated_milestones(boundaries, validated):
            _validate_milestone(boundary, project_name, save_traces)

        if builder_done:
            # Drain any milestones that appeared while we were validating
            _drain_remaining_milestones(project_name, save_traces)
            now = datetime.now().strftime("%H:%M:%S")
            log("validator", f"[{now}] Builder finished. Shutting down.", style="bold green")
            break

        time.sleep(interval)
