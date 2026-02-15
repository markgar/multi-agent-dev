"""Planner commands: backlog planning and milestone planning."""

import os

import typer

from agent.milestone import get_tasks_per_milestone
from agent.prompts import (
    PLANNER_COMPLETENESS_PROMPT,
    PLANNER_INITIAL_PROMPT,
    PLANNER_PROMPT,
    PLANNER_SPLIT_PROMPT,
)
from agent.utils import log, run_copilot


_MAX_TASKS_PER_MILESTONE = 10


def register(app: typer.Typer) -> None:
    """Register planner commands on the shared app."""
    app.command()(plan)


def plan(requirements_changed: bool = False) -> None:
    """Run the planner to create or update TASKS.md based on SPEC.md."""
    log("planner", "")
    log("planner", "[Planner] Evaluating project state...", style="magenta")
    log("planner", "")

    is_fresh = not os.path.exists("BACKLOG.md")

    if is_fresh:
        # Case A: fresh project — create backlog and first milestone
        log("planner", "[Backlog Planner] Fresh project — creating backlog and first milestone...", style="magenta")
        exit_code = run_copilot("planner", PLANNER_INITIAL_PROMPT)
        if exit_code != 0:
            log("planner", "")
            log("planner", "======================================", style="bold red")
            log("planner", " Planner failed! Check errors above", style="bold red")
            log("planner", "======================================", style="bold red")
            return

        # Completeness pass: validate backlog covers all requirements
        log("planner", "")
        log("planner", "[Backlog Planner] Running completeness check on backlog...", style="magenta")
        exit_code = run_copilot("planner", PLANNER_COMPLETENESS_PROMPT)
        if exit_code != 0:
            log("planner", "[Backlog Planner] WARNING: Completeness check failed. Continuing with existing backlog.", style="bold yellow")
    else:
        # Case B/C: continuing or evolving project
        prompt = PLANNER_PROMPT
        if requirements_changed:
            prefix = (
                "IMPORTANT: REQUIREMENTS.md was JUST updated with new requirements this session. "
                "This is almost certainly Case C — new features or changes were added. "
                "Compare REQUIREMENTS.md against the BACKLOG.md story list and SPEC.md technical "
                "decisions to identify new stories that need adding. Do NOT conclude that "
                "'everything is already covered' without checking each requirement against "
                "the backlog and existing milestones.\n\n"
            )
            prompt = prefix + PLANNER_PROMPT

        exit_code = run_copilot("planner", prompt)
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


def check_milestone_sizes() -> None:
    """If any uncompleted milestone exceeds the task limit, ask the planner to split it."""
    oversized = [
        ms for ms in get_tasks_per_milestone("TASKS.md")
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
            task_count=ms["task_count"],
        )
        run_copilot("planner", prompt)

    # Verify once — if still oversized after one attempt, log a warning and proceed
    if oversized:
        still_oversized = [
            ms for ms in get_tasks_per_milestone("TASKS.md")
            if ms["task_count"] > _MAX_TASKS_PER_MILESTONE
        ]
        for ms in still_oversized:
            log(
                "planner",
                f"WARNING: Milestone '{ms['name']}' still has {ms['task_count']} tasks after split attempt.",
                style="red",
            )
