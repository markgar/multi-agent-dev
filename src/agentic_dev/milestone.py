"""Milestone parsing, boundary tracking, and per-agent milestone checkpoints."""

import os
import re

from agentic_dev.utils import resolve_logs_dir, run_cmd

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


def parse_milestone_log(text: str) -> list[dict]:
    """Parse milestone log text into boundary dicts.

    Pure function: takes raw text, returns structured data.
    Format per line: name|start_sha|end_sha
    """
    boundaries = []
    for line in text.strip().split("\n"):
        parts = line.strip().split("|")
        if len(parts) == 3:
            boundaries.append({
                "name": parts[0],
                "start_sha": parts[1],
                "end_sha": parts[2],
            })
    return boundaries


def load_milestone_boundaries() -> list[dict]:
    """Load all recorded milestone boundaries from logs/milestones.log.

    Returns a list of dicts: [{"name": str, "start_sha": str, "end_sha": str}, ...]
    in the order they were recorded.
    """
    try:
        logs_dir = resolve_logs_dir()
        path = os.path.join(logs_dir, _MILESTONE_LOG_FILE)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return parse_milestone_log(f.read())
    except Exception:
        pass
    return []


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
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                name = line.strip()
                if name:
                    reviewed.add(name)
    except Exception:
        pass
    return reviewed


def parse_milestones_from_text(content: str) -> list[dict]:
    """Parse milestone markdown text and return every milestone with its task counts.

    Pure function: takes raw markdown content, returns structured data.
    Returns a list of dicts in document order:
        [{"name": str, "done": int, "total": int}, ...]

    A milestone section starts with '# Milestone: <name>' or '## Milestone: <name>'.
    An optional number/label (e.g. '01', '1a') may appear between 'Milestone' and
    the colon: '# Milestone 01: <name>'.
    Contains checkbox lines like '- [x] ...' or '- [ ] ...'.
    """
    milestones = []
    current_name = None
    total = 0
    done = 0

    for line in content.split("\n"):
        heading_match = re.match(r"^#{1,2}\s+Milestone(?:\s+\S+)?:\s*(.+)$", line, re.IGNORECASE)
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


def _parse_milestones(tasks_path: str) -> list[dict]:
    """Read TASKS.md and parse milestones. Thin I/O wrapper around parse_milestones_from_text."""
    if not os.path.exists(tasks_path):
        return []
    with open(tasks_path, "r", encoding="utf-8") as f:
        return parse_milestones_from_text(f.read())


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


def has_unexpanded_stories(content: str) -> bool:
    """Return True if the ## Roadmap section has any non-strikethrough story bullets."""
    in_roadmap = False
    for line in content.split("\n"):
        if re.match(r"^##\s+Roadmap", line, re.IGNORECASE):
            in_roadmap = True
            continue
        if in_roadmap and line.startswith("## "):
            break
        if in_roadmap and re.match(r"^\d+\.\s+", line):
            if "~~" not in line:
                return True
    return False


def has_unexpanded_stories_in_file(tasks_path: str) -> bool:
    """I/O wrapper for has_unexpanded_stories."""
    if not os.path.exists(tasks_path):
        return False
    with open(tasks_path, "r", encoding="utf-8") as f:
        return has_unexpanded_stories(f.read())


def count_unstarted_milestones(content: str) -> int:
    """Count milestones where no tasks are completed (done == 0)."""
    return sum(1 for ms in parse_milestones_from_text(content) if ms["done"] == 0)


def count_unstarted_milestones_in_file(tasks_path: str) -> int:
    """I/O wrapper for count_unstarted_milestones."""
    if not os.path.exists(tasks_path):
        return 0
    with open(tasks_path, "r", encoding="utf-8") as f:
        return count_unstarted_milestones(f.read())


def get_tasks_per_milestone(tasks_path: str) -> list[dict]:
    """Return task counts for each uncompleted milestone.

    Returns: [{"name": str, "task_count": int}, ...]
    """
    return [
        {"name": ms["name"], "task_count": ms["total"]}
        for ms in _parse_milestones(tasks_path)
        if ms["done"] < ms["total"]
    ]


# ============================================
# Backlog parsing
# ============================================

_BACKLOG_RE = re.compile(
    r"^(\d+)\.\s+\[([ xX~]|\d+)\]\s+(.+?)(?:\s*<!--\s*depends:\s*([\d,\s]+)\s*-->)?$"
)


def parse_backlog(content: str) -> list[dict]:
    """Parse BACKLOG.md content into structured story dicts.

    Each line: ``N. [x] Story name <!-- depends: 1, 2 -->``
    Three-state checkboxes: [ ] = unclaimed, [N] = claimed by builder N, [x] = completed.
    Returns: [{"number": int, "name": str, "checked": bool, "status": str, "depends": list[int]}]
    The ``checked`` field is True for both [N] and [x] (backward compat).
    The ``status`` field is one of: "unclaimed", "in_progress", "completed".
    """
    stories = []
    for line in content.split("\n"):
        m = _BACKLOG_RE.match(line.strip())
        if not m:
            continue
        number = int(m.group(1))
        marker = m.group(2).strip().lower()
        if marker == "x":
            status = "completed"
        elif marker == "~" or marker.isdigit():
            status = "in_progress"
        else:
            status = "unclaimed"
        checked = status != "unclaimed"
        name = m.group(3).strip()
        deps_raw = m.group(4)
        depends = []
        if deps_raw:
            depends = [int(d.strip()) for d in deps_raw.split(",") if d.strip()]
        stories.append({
            "number": number,
            "name": name,
            "checked": checked,
            "status": status,
            "depends": depends,
        })
    return stories


def has_pending_backlog_stories(content: str) -> bool:
    """Return True if there is at least one unchecked story in the backlog."""
    return any(not s["checked"] for s in parse_backlog(content))


def get_next_eligible_story(content: str) -> dict | None:
    """Return the first unclaimed story whose dependencies are all completed.

    Only stories with status "unclaimed" are candidates. Dependencies are
    satisfied only by status "completed" — "in_progress" does NOT count.
    Returns None if all stories are done/claimed or if remaining stories
    have unmet dependencies (deadlock).
    """
    stories = parse_backlog(content)
    completed_numbers = {s["number"] for s in stories if s["status"] == "completed"}
    for story in stories:
        if story["status"] != "unclaimed":
            continue
        if all(dep in completed_numbers for dep in story["depends"]):
            return story
    return None


def has_pending_backlog_stories_in_file(path: str) -> bool:
    """I/O wrapper for has_pending_backlog_stories. Returns False if file missing."""
    try:
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            return has_pending_backlog_stories(f.read())
    except Exception:
        return False


def get_next_eligible_story_in_file(path: str) -> dict | None:
    """I/O wrapper for get_next_eligible_story. Returns None if file missing."""
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return get_next_eligible_story(f.read())
    except Exception:
        return None


# ============================================
# Milestone file parsing (milestones/ directory)
# ============================================


import glob


def parse_milestone_file(path: str) -> dict | None:
    """Read one milestone file and return milestone info.

    Returns {"name": str, "done": int, "total": int, "all_done": bool}
    or None if the file doesn't exist or has no tasks.

    The file format has a # Milestone: or ## Milestone: heading,
    an optional validates block, and checkbox lines.
    """
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    milestones = parse_milestones_from_text(content)
    if not milestones:
        return None

    ms = milestones[0]
    return {
        "name": ms["name"],
        "done": ms["done"],
        "total": ms["total"],
        "all_done": ms["done"] == ms["total"],
    }


def list_milestone_files(milestones_dir: str = "milestones") -> list[str]:
    """Return sorted list of .md file paths in the milestones/ directory.

    Returns full paths, sorted alphabetically. Returns empty list if
    the directory doesn't exist.
    """
    if not os.path.isdir(milestones_dir):
        return []
    pattern = os.path.join(milestones_dir, "*.md")
    return sorted(glob.glob(pattern))


def get_all_milestones(milestones_dir: str = "milestones") -> list[dict]:
    """Parse all milestone files and return milestone info for each.

    Returns [{"name": str, "done": int, "total": int, "all_done": bool, "path": str}, ...]
    in filename-sorted order. Skips files that fail to parse.
    """
    results = []
    for path in list_milestone_files(milestones_dir):
        ms = parse_milestone_file(path)
        if ms is not None:
            ms["path"] = path
            results.append(ms)
    return results


def get_completed_milestones_from_dir(milestones_dir: str = "milestones") -> list[dict]:
    """Return only completed milestones from the milestones/ directory.

    Returns [{"name": str, "all_done": True}, ...] for milestones where
    all tasks are checked.
    """
    return [
        {"name": ms["name"], "all_done": True}
        for ms in get_all_milestones(milestones_dir)
        if ms["all_done"]
    ]


def get_milestone_progress_from_file(path: str) -> dict | None:
    """Return progress info for a single milestone file.

    Returns {"name": str, "done": int, "total": int} if the milestone
    has unchecked tasks. Returns None if all tasks are done or file
    doesn't exist.
    """
    ms = parse_milestone_file(path)
    if ms is None or ms["all_done"]:
        return None
    return {"name": ms["name"], "done": ms["done"], "total": ms["total"]}


def get_tasks_per_milestone_from_dir(milestones_dir: str = "milestones") -> list[dict]:
    """Return task counts for each uncompleted milestone in the directory.

    Returns [{"name": str, "task_count": int, "path": str}, ...]
    Replacement for get_tasks_per_milestone("TASKS.md").
    """
    return [
        {"name": ms["name"], "task_count": ms["total"], "path": ms["path"]}
        for ms in get_all_milestones(milestones_dir)
        if not ms["all_done"]
    ]
