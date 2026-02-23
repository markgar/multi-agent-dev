"""Planner commands: backlog planning and milestone planning."""

import os
import re

import typer

from agentic_dev.backlog_checker import check_backlog_quality, run_ordering_check
from agentic_dev.git_helpers import git_push_with_retry
from agentic_dev.milestone import get_tasks_per_milestone_from_dir, list_milestone_files, parse_backlog
from agentic_dev.prompts import (
    PLANNER_COMPLETENESS_PROMPT,
    PLANNER_INITIAL_PROMPT,
    PLANNER_PROMPT,
    PLANNER_SPLIT_PROMPT,
)
from agentic_dev.utils import log, run_cmd, run_copilot


_MAX_TASKS_PER_MILESTONE = 8

# Regex matching the first story line in BACKLOG.md: "1. [ ] Story name"
_FIRST_STORY_RE = re.compile(r"^(1\.\s+)\[ \](.*)$", re.MULTILINE)


def _ensure_first_story_checked() -> None:
    """Mark story #1 as [x] in BACKLOG.md if a milestone file exists.

    The planner prompt tells the LLM not to manage checkboxes — the Python
    orchestration owns that. After the initial plan creates BACKLOG.md and
    the first milestone file, this function checks off story #1 so the
    structural checker passes and the builder knows story #1 is planned.
    """
    if not os.path.exists("BACKLOG.md"):
        return
    if not list_milestone_files("milestones"):
        return

    with open("BACKLOG.md", "r", encoding="utf-8") as f:
        content = f.read()

    if not _FIRST_STORY_RE.search(content):
        return  # Already checked or no matching line

    updated = _FIRST_STORY_RE.sub(r"\1[x]\2", content, count=1)
    with open("BACKLOG.md", "w", encoding="utf-8") as f:
        f.write(updated)

    run_cmd(["git", "add", "BACKLOG.md"], quiet=True)
    run_cmd(
        ["git", "commit", "-m", "[planner] Check off story #1 (milestone planned)"],
        quiet=True,
    )
    git_push_with_retry("planner")
    log("planner", "[Planner] Checked off story #1 in BACKLOG.md", style="green")


def register(app: typer.Typer) -> None:
    """Register planner commands on the shared app."""
    app.command()(plan)


def _get_first_story_name() -> str:
    """Extract the name of story #1 from BACKLOG.md.

    Returns the story name for passing to the milestone planner prompt.
    Falls back to a generic label if BACKLOG.md can't be read or parsed.
    """
    if not os.path.exists("BACKLOG.md"):
        return "the first story"
    try:
        with open("BACKLOG.md", "r", encoding="utf-8") as f:
            content = f.read()
        stories = parse_backlog(content)
        if stories:
            return stories[0]["name"]
    except (OSError, IndexError):
        pass
    return "the first story"


def plan(requirements_changed: bool = False, story_name: str = "") -> bool:
    """Run the planner to create or update milestones based on SPEC.md.

    When story_name is provided, it is interpolated into the PLANNER_PROMPT
    so the LLM knows which story to expand.

    Returns True if planning succeeded, False if it failed.
    """
    log("planner", "")
    log("planner", "[Planner] Evaluating project state...", style="magenta")
    log("planner", "")

    # Ensure milestones/ directory exists before any planner invocation
    os.makedirs("milestones", exist_ok=True)

    is_fresh = not os.path.exists("BACKLOG.md")

    if is_fresh:
        # Case A: fresh project — create backlog, validate, then plan first milestone
        log("planner", "[Backlog Planner] Fresh project — creating backlog...", style="magenta")
        exit_code = run_copilot("planner", PLANNER_INITIAL_PROMPT)
        if exit_code != 0:
            log("planner", "")
            log("planner", "======================================", style="bold red")
            log("planner", " Planner failed! Check errors above", style="bold red")
            log("planner", "======================================", style="bold red")
            return False

        # Completeness pass: validate backlog covers all requirements
        log("planner", "")
        log("planner", "[Backlog Planner] Running completeness check on backlog...", style="magenta")
        exit_code = run_copilot("planner", PLANNER_COMPLETENESS_PROMPT)
        if exit_code != 0:
            log("planner", "[Backlog Planner] WARNING: Completeness check failed. Continuing with existing backlog.", style="bold yellow")

        # Quality gate: structural checks + LLM quality review
        quality_ok = check_backlog_quality()
        if not quality_ok:
            log("planner", "[Backlog Planner] Structural issues detected — re-running initial planner...", style="yellow")
            exit_code = run_copilot("planner", PLANNER_INITIAL_PROMPT)
            if exit_code != 0:
                log("planner", "[Backlog Planner] Re-plan failed. Continuing with existing backlog.", style="bold yellow")
            else:
                # Re-check after re-plan (non-blocking — just log results)
                check_backlog_quality()

        # Ordering pass: ensure stories are in topological dependency order
        run_ordering_check()

        # Plan the first milestone now that backlog quality is confirmed
        first_story_name = _get_first_story_name()
        log("planner", "")
        log("planner", f"[Backlog Planner] Planning first milestone: {first_story_name}...", style="magenta")
        milestone_prompt = PLANNER_PROMPT.format(story_name=first_story_name)
        exit_code = run_copilot("planner", milestone_prompt)
        if exit_code != 0:
            log("planner", "[Backlog Planner] First milestone planning failed.", style="bold red")
            return False

        # Mark story #1 as checked now that its milestone exists
        _ensure_first_story_checked()
    else:
        # Case B/C: continuing or evolving project
        prompt = PLANNER_PROMPT.format(story_name=story_name if story_name else "the next eligible story")
        if requirements_changed:
            prefix = (
                "IMPORTANT: REQUIREMENTS.md was JUST updated with new requirements this session. "
                "This is almost certainly Case C — new features or changes were added. "
                "Compare REQUIREMENTS.md against the BACKLOG.md story list and SPEC.md technical "
                "decisions to identify new stories that need adding. Do NOT conclude that "
                "'everything is already covered' without checking each requirement against "
                "the backlog and existing milestones.\n\n"
            )
            prompt = prefix + prompt

        exit_code = run_copilot("planner", prompt)
        if exit_code != 0:
            log("planner", "")
            log("planner", "======================================", style="bold red")
            log("planner", " Planner failed! Check errors above", style="bold red")
            log("planner", "======================================", style="bold red")
            return False

    log("planner", "")
    log("planner", "======================================", style="bold magenta")
    log("planner", " Plan updated!", style="bold magenta")
    log("planner", "======================================", style="bold magenta")
    return True


def check_milestone_sizes() -> None:
    """If any uncompleted milestone exceeds the task limit, ask the planner to split it."""
    oversized = [
        ms for ms in get_tasks_per_milestone_from_dir("milestones")
        if ms["task_count"] > _MAX_TASKS_PER_MILESTONE
    ]
    for ms in oversized:
        log(
            "planner",
            f"Milestone '{ms['name']}' has {ms['task_count']} tasks (max {_MAX_TASKS_PER_MILESTONE}). "
            f"Asking planner to split it...",
            style="yellow",
        )
        prompt = PLANNER_SPLIT_PROMPT.format(
            milestone_name=ms["name"],
            milestone_file=ms["path"],
            task_count=ms["task_count"],
        )
        run_copilot("planner", prompt)

    # Verify once — if still oversized after one attempt, log a warning and proceed
    if oversized:
        still_oversized = [
            ms for ms in get_tasks_per_milestone_from_dir("milestones")
            if ms["task_count"] > _MAX_TASKS_PER_MILESTONE
        ]
        for ms in still_oversized:
            log(
                "planner",
                f"WARNING: Milestone '{ms['name']}' still has {ms['task_count']} tasks after split attempt.",
                style="red",
            )
