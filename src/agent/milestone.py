"""Milestone parsing, boundary tracking, and per-agent milestone checkpoints."""

import os
import re

from agent.utils import resolve_logs_dir, run_cmd

_MILESTONE_CHECKPOINT_FILE = "reviewer.milestone"
_MILESTONE_LOG_FILE = "milestones.log"


def record_milestone_boundary(name: str, start_sha: str, end_sha: str) -> None:
    """Append a completed milestone's SHA range to logs/milestones.log.

    This is the shared source of truth for milestone boundaries.
    Written by the build loop (deterministic code, not prompts).
    Format: name|start_sha|end_sha
    """
    try:
        logs_dir = resolve_logs_dir()
        path = os.path.join(logs_dir, _MILESTONE_LOG_FILE)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{name}|{start_sha}|{end_sha}\n")
    except Exception:
        pass


def load_milestone_boundaries() -> list[dict]:
    """Load all recorded milestone boundaries from logs/milestones.log.

    Returns a list of dicts: [{"name": str, "start_sha": str, "end_sha": str}, ...]
    in the order they were recorded.
    """
    boundaries = []
    try:
        logs_dir = resolve_logs_dir()
        path = os.path.join(logs_dir, _MILESTONE_LOG_FILE)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("|")
                    if len(parts) == 3:
                        boundaries.append({
                            "name": parts[0],
                            "start_sha": parts[1],
                            "end_sha": parts[2],
                        })
    except Exception:
        pass
    return boundaries


def get_last_milestone_end_sha() -> str:
    """Return the end SHA of the most recently completed milestone.

    Falls back to the initial bootstrap commit (root commit) if no milestones
    have been recorded yet.
    """
    boundaries = load_milestone_boundaries()
    if boundaries:
        return boundaries[-1]["end_sha"]

    # Fallback: the very first commit in the repo (bootstrap commit)
    result = run_cmd(
        ["git", "rev-list", "--max-parents=0", "HEAD"],
        capture=True,
    )
    if result.returncode == 0:
        # May return multiple roots; take the first
        lines = result.stdout.strip().split("\n")
        return lines[0].strip() if lines else ""
    return ""


def save_milestone_checkpoint(milestone_name: str, checkpoint_file: str = None) -> None:
    """Record that an agent has processed a milestone.

    Args:
        milestone_name: Name of the milestone that was processed.
        checkpoint_file: Filename for the checkpoint (defaults to reviewer.milestone).
    """
    if checkpoint_file is None:
        checkpoint_file = _MILESTONE_CHECKPOINT_FILE
    try:
        logs_dir = resolve_logs_dir()
        path = os.path.join(logs_dir, checkpoint_file)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{milestone_name}\n")
    except Exception:
        pass


def load_reviewed_milestones(checkpoint_file: str = None) -> set[str]:
    """Return the set of milestone names an agent has already processed.

    Args:
        checkpoint_file: Filename for the checkpoint (defaults to reviewer.milestone).
    """
    if checkpoint_file is None:
        checkpoint_file = _MILESTONE_CHECKPOINT_FILE
    reviewed = set()
    try:
        logs_dir = resolve_logs_dir()
        path = os.path.join(logs_dir, checkpoint_file)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    name = line.strip()
                    if name:
                        reviewed.add(name)
    except Exception:
        pass
    return reviewed


def _parse_milestones(tasks_path: str) -> list[dict]:
    """Parse TASKS.md and return every milestone with its task counts.

    Returns a list of dicts in document order:
        [{"name": str, "done": int, "total": int}, ...]

    A milestone section starts with '## Milestone: <name>' and contains
    checkbox lines like '- [x] ...' or '- [ ] ...'.
    """
    milestones = []
    if not os.path.exists(tasks_path):
        return milestones

    with open(tasks_path, "r", encoding="utf-8") as f:
        content = f.read()

    current_name = None
    total = 0
    done = 0

    for line in content.split("\n"):
        heading_match = re.match(r"^##\s+Milestone:\s*(.+)$", line, re.IGNORECASE)
        if heading_match:
            if current_name and total > 0:
                milestones.append({"name": current_name, "done": done, "total": total})
            current_name = heading_match.group(1).strip()
            total = 0
            done = 0
            continue

        if current_name:
            if re.search(r"\[x\]", line, re.IGNORECASE):
                total += 1
                done += 1
            elif re.search(r"\[ \]", line):
                total += 1

    if current_name and total > 0:
        milestones.append({"name": current_name, "done": done, "total": total})

    return milestones


def get_completed_milestones(tasks_path: str) -> list[dict]:
    """Return milestones with an all_done flag.

    Returns: [{"name": str, "all_done": bool}, ...]
    """
    return [
        {"name": ms["name"], "all_done": ms["done"] == ms["total"]}
        for ms in _parse_milestones(tasks_path)
    ]


def get_current_milestone_progress(tasks_path: str) -> dict | None:
    """Return progress info for the first incomplete milestone.

    Returns {"name": str, "done": int, "total": int}, or None if all complete.
    """
    for ms in _parse_milestones(tasks_path):
        if ms["done"] < ms["total"]:
            return ms
    return None


def get_tasks_per_milestone(tasks_path: str) -> list[dict]:
    """Return task counts for each uncompleted milestone.

    Returns: [{"name": str, "task_count": int}, ...]
    """
    return [
        {"name": ms["name"], "task_count": ms["total"]}
        for ms in _parse_milestones(tasks_path)
        if ms["done"] < ms["total"]
    ]
