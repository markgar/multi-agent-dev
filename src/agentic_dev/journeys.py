"""Journey parsing, eligibility filtering, and greedy set-cover selection.

JOURNEYS.md is a planner-generated artifact that describes multi-step user
flows. Each journey becomes eligible when its ``after`` story is completed in
BACKLOG.md, and the greedy selector picks the smallest set of journeys that
covers all reachable feature tags.
"""

import re
from dataclasses import dataclass, field

from agentic_dev.milestone import parse_backlog


# ============================================
# Data types
# ============================================

@dataclass
class Journey:
    """A single parsed user journey from JOURNEYS.md."""
    id: str            # e.g. "J-1"
    title: str         # e.g. "Admin navigates all sidebar links"
    after: int         # story number that must be [x] before this journey is eligible
    covers: set[str]   # feature-coverage tags, e.g. {"venues.crud", "navigation"}
    tags: set[str]     # optional labels like "smoke"
    description: str   # natural-language steps


# ============================================
# Parsing
# ============================================

_JOURNEY_HEADING_RE = re.compile(
    r"^##\s+(J-\d+):\s*(.+)$"
)
_AFTER_RE = re.compile(
    r"<!--\s*after:\s*(\d+)\s*-->"
)
_COVERS_RE = re.compile(
    r"<!--\s*covers:\s*(.+?)\s*-->"
)
_TAGS_RE = re.compile(
    r"<!--\s*tags:\s*(.+?)\s*-->"
)


def parse_journeys(content: str) -> list[Journey]:
    """Parse JOURNEYS.md content into a list of Journey objects.

    Pure function: takes raw markdown, returns structured data.
    Journeys missing required fields (after, covers) are skipped with a
    warning-level note in the returned list (no side effects).
    """
    journeys: list[Journey] = []
    current_id: str | None = None
    current_title: str = ""
    current_after: int | None = None
    current_covers: set[str] = set()
    current_tags: set[str] = set()
    description_lines: list[str] = []

    def _flush() -> None:
        if current_id is not None and current_after is not None and current_covers:
            desc = "\n".join(description_lines).strip()
            journeys.append(Journey(
                id=current_id,
                title=current_title,
                after=current_after,
                covers=set(current_covers),
                tags=set(current_tags),
                description=desc,
            ))

    for line in content.split("\n"):
        heading_match = _JOURNEY_HEADING_RE.match(line.strip())
        if heading_match:
            _flush()
            current_id = heading_match.group(1)
            current_title = heading_match.group(2).strip()
            current_after = None
            current_covers = set()
            current_tags = set()
            description_lines = []
            continue

        if current_id is None:
            continue

        after_match = _AFTER_RE.search(line)
        if after_match:
            current_after = int(after_match.group(1))
            continue

        covers_match = _COVERS_RE.search(line)
        if covers_match:
            current_covers = {t.strip() for t in covers_match.group(1).split(",") if t.strip()}
            continue

        tags_match = _TAGS_RE.search(line)
        if tags_match:
            current_tags = {t.strip() for t in tags_match.group(1).split(",") if t.strip()}
            continue

        # Remaining non-empty lines are description
        if line.strip():
            description_lines.append(line.strip())

    _flush()
    return journeys


# ============================================
# Eligibility filtering
# ============================================


def get_completed_story_numbers(backlog_content: str) -> set[int]:
    """Return the set of story numbers marked [x] in BACKLOG.md content.

    Pure function: delegates to parse_backlog and filters by status.
    """
    stories = parse_backlog(backlog_content)
    return {s["number"] for s in stories if s["status"] == "completed"}


def filter_eligible_journeys(journeys: list[Journey], completed_stories: set[int]) -> list[Journey]:
    """Return only journeys whose ``after`` story is in the completed set.

    Pure function: no side effects.
    """
    return [j for j in journeys if j.after in completed_stories]


# ============================================
# Greedy set-cover selection
# ============================================


def select_journeys(eligible: list[Journey]) -> list[Journey]:
    """Pick the minimum set of journeys that covers all reachable feature tags.

    Uses a greedy set-cover algorithm:
    1. Compute the universe of all feature tags across eligible journeys.
    2. Repeatedly pick the journey that covers the most uncovered tags.
    3. Stop when all tags are covered (or no eligible journey adds new coverage).

    Journeys whose tags are a subset of already-covered tags are automatically
    retired — they never get selected because they add zero new coverage.

    Ties are broken by journey ID (alphabetical) for determinism.

    Returns selected journeys in the order they were picked.
    """
    if not eligible:
        return []

    universe = set()
    for j in eligible:
        universe |= j.covers

    covered: set[str] = set()
    selected: list[Journey] = []
    remaining = list(eligible)

    while covered != universe and remaining:
        # Sort by: most new coverage (desc), then by ID (asc) for determinism
        remaining.sort(key=lambda j: (-len(j.covers - covered), j.id))
        best = remaining[0]
        new_coverage = best.covers - covered
        if not new_coverage:
            break
        selected.append(best)
        covered |= best.covers
        remaining = [j for j in remaining[1:] if j.covers - covered]

    return selected


# ============================================
# End-to-end convenience: parse + filter + select
# ============================================


def select_journeys_for_milestone(
    journeys_content: str,
    backlog_content: str,
) -> list[Journey]:
    """Parse JOURNEYS.md and BACKLOG.md, return the selected journeys for validation.

    This is the main entry point called by the validator. It chains:
    parse → filter by completed stories → greedy set-cover selection.

    Returns an empty list if JOURNEYS.md is empty, unparseable, or no
    journeys are eligible yet.
    """
    journeys = parse_journeys(journeys_content)
    if not journeys:
        return []

    completed = get_completed_story_numbers(backlog_content)
    eligible = filter_eligible_journeys(journeys, completed)
    return select_journeys(eligible)


def format_journey_prompt_block(journeys: list[Journey]) -> str:
    """Format selected journeys into a prompt section for the validator LLM.

    Returns a string ready to be interpolated into the validator prompt.
    Each journey is formatted as:
        J-N: Title
        Steps: <description>

    Returns empty string if no journeys are provided.
    """
    if not journeys:
        return ""

    lines = []
    for j in journeys:
        lines.append(f"  {j.id}: {j.title}")
        lines.append(f"  Steps: {j.description}")
        lines.append("")
    return "\n".join(lines)
