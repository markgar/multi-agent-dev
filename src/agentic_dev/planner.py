"""Planner commands: backlog planning and milestone planning."""

import os

import typer

from agentic_dev.backlog_checker import check_backlog_quality, run_ordering_check
from agentic_dev.milestone import get_tasks_per_milestone_from_dir
from agentic_dev.prompts import (
    PLANNER_COMPLETENESS_PROMPT,
    PLANNER_INITIAL_PROMPT,
    PLANNER_JOURNEYS_PROMPT,
    PLANNER_PROMPT,
    PLANNER_SPLIT_PROMPT,
)
from agentic_dev.utils import log, run_cmd, run_copilot


_MAX_TASKS_PER_MILESTONE = 8

def register(app: typer.Typer) -> None:
    """Register planner commands on the shared app."""
    app.command()(plan)


def plan(requirements_changed: bool = False, story_name: str = "", model: str = "") -> bool:
    """Run the planner to create or update milestones based on SPEC.md.

    When story_name is provided, it is interpolated into the PLANNER_PROMPT
    so the LLM knows which story to expand.

    When *model* is provided it is forwarded to every ``run_copilot`` call,
    overriding the COPILOT_MODEL environment variable.

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
        exit_code = run_copilot("planner", PLANNER_INITIAL_PROMPT, model=model)
        if exit_code != 0:
            log("planner", "")
            log("planner", "======================================", style="bold red")
            log("planner", " Planner failed! Check errors above", style="bold red")
            log("planner", "======================================", style="bold red")
            return False

        # Completeness pass: validate backlog covers all requirements
        log("planner", "")
        log("planner", "[Backlog Planner] Running completeness check on backlog...", style="magenta")
        exit_code = run_copilot("planner", PLANNER_COMPLETENESS_PROMPT, model=model)
        if exit_code != 0:
            log("planner", "[Backlog Planner] WARNING: Completeness check failed. Continuing with existing backlog.", style="bold yellow")

        # Quality gate: structural checks + LLM quality review
        quality_ok = check_backlog_quality(model=model)
        if not quality_ok:
            log("planner", "[Backlog Planner] Structural issues detected — re-running initial planner...", style="yellow")
            try:
                exit_code = run_copilot("planner", PLANNER_INITIAL_PROMPT, model=model)
            except Exception as e:
                log("planner", f"[Backlog Planner] Re-plan crashed: {e}", style="bold red")
                log("planner", "")
                log("planner", "======================================", style="bold red")
                log("planner", " Planner could not produce a valid plan. Stopping.", style="bold red")
                log("planner", "======================================", style="bold red")
                return False
            if exit_code != 0:
                log("planner", "")
                log("planner", "======================================", style="bold red")
                log("planner", " Re-plan failed. Planner could not produce a valid plan. Stopping.", style="bold red")
                log("planner", "======================================", style="bold red")
                return False

            # Re-check after re-plan — if still failing, stop
            quality_ok_2 = check_backlog_quality(model=model)
            if not quality_ok_2:
                log("planner", "")
                log("planner", "======================================", style="bold red")
                log("planner", " Planner could not resolve structural issues after re-plan. Stopping.", style="bold red")
                log("planner", "======================================", style="bold red")
                return False

        # Ordering pass: ensure stories are in topological dependency order
        run_ordering_check(model=model)

        # Journeys pass: create JOURNEYS.md for the validator
        if not os.path.exists("JOURNEYS.md"):
            log("planner", "")
            log("planner", "[Backlog Planner] Creating user journeys (JOURNEYS.md)...", style="magenta")
            journeys_exit = run_copilot("planner", PLANNER_JOURNEYS_PROMPT, model=model)
            if journeys_exit != 0:
                log("planner", "[Backlog Planner] WARNING: JOURNEYS.md creation failed. Validator will use legacy scope.", style="bold yellow")

        # Builders will claim story #1 and plan its milestone — no milestone
        # planning here. The orchestrator only owns backlog creation.
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

        exit_code = run_copilot("planner", prompt, model=model)
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


def check_milestone_sizes(model: str = "") -> None:
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
        run_copilot("planner", prompt, model=model)

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
