"""Backlog quality checker: deterministic and LLM checks for backlog planner output.

Runs after the backlog planner creates BACKLOG.md and the first milestone in milestones/.
Deterministic checks (A1-A4, B) validate structure and proportionality.
LLM quality check (C1-C7, C5b) evaluates story semantics via a single Copilot call.
"""

import os
import re

from agentic_dev.milestone import list_milestone_files, parse_backlog, parse_milestones_from_text
from agentic_dev.prompts import BACKLOG_ORDERING_PROMPT, BACKLOG_QUALITY_PROMPT
from agentic_dev.utils import log, run_copilot


# Keywords that indicate a test-only story (primary activity, not incidental)
_TEST_KEYWORDS = re.compile(
    r"\b(unit\s+tests?|integration\s+tests?|e2e\s+tests?|test\s+suite|test\s+coverage"
    r"|write\s+tests?|add\s+tests?)\b",
    re.IGNORECASE,
)

# Keywords that indicate a container/deployment-only story
_CONTAINER_KEYWORDS = re.compile(
    r"\b(dockerfile|docker-compose|docker\s+container|containeriz|deployment\s+pipeline"
    r"|ci/cd|ci\s+pipeline|cd\s+pipeline)\b",
    re.IGNORECASE,
)

# Keywords that indicate pre-planned refactoring
_REFACTOR_KEYWORDS = re.compile(
    r"\b(refactor|cleanup|code\s+quality|technical\s+debt)\b",
    re.IGNORECASE,
)

# Features proxy: headings in REQUIREMENTS.md
_HEADING_RE = re.compile(r"^#{2,3}\s+", re.MULTILINE)

# Feature entity/endpoint/page mentions
_ENTITY_RE = re.compile(r"\b(?:Create|Add|Implement)\s+([A-Z][a-zA-Z]+)")
_ENDPOINT_RE = re.compile(r"/api/\S+")
_PAGE_RE = re.compile(r"\b(?:page|view|screen|dashboard|form)\b", re.IGNORECASE)


# ============================================
# Individual check functions (pure)
# ============================================


def check_backlog_heading(backlog_text: str) -> str | None:
    """A1: Check that BACKLOG.md starts with a heading containing 'Backlog'.

    Returns a warning message or None if pass.
    """
    first_line = backlog_text.strip().split("\n")[0] if backlog_text.strip() else ""
    if not re.match(r"^#\s+.*[Bb]acklog", first_line):
        return "BACKLOG.md does not start with a '# ... Backlog' heading (cosmetic)"
    return None


def check_story_format(stories: list[dict], backlog_text: str) -> list[str]:
    """A1: Check that every story line matches expected format.

    Returns a list of failure messages. Empty list = pass.
    """
    failures = []
    if not stories:
        failures.append("BACKLOG.md contains no parseable stories")
        return failures

    # Check that the first story is checked
    if not stories[0]["checked"]:
        failures.append(
            f"Story #1 ('{stories[0]['name']}') is not checked [x] — "
            "the first milestone won't be planned"
        )

    # Check sequential numbering (warn, don't re-plan)
    expected = 1
    for story in stories:
        if story["number"] != expected:
            failures.append(
                f"Story numbering is not sequential: expected {expected}, "
                f"got {story['number']}"
            )
            break
        expected += 1

    # Check that every story has a depends annotation in the raw text
    # parse_backlog returns empty depends list for both "depends: none" and missing annotation
    # We need to check the raw text for missing annotations
    for story in stories:
        pattern = re.compile(
            rf"^{story['number']}\.\s+\[[ xX]\].*<!--\s*depends:",
            re.MULTILINE,
        )
        if not pattern.search(backlog_text):
            failures.append(
                f"Story #{story['number']} ('{story['name']}') is missing "
                "a <!-- depends: ... --> annotation"
            )

    return failures


def check_dependency_graph(stories: list[dict]) -> list[str]:
    """A2: Validate dependency references and check for cycles.

    Returns a list of failure messages. Empty list = pass.
    """
    failures = []
    story_numbers = {s["number"] for s in stories}

    # Check all deps reference existing stories
    for story in stories:
        for dep in story["depends"]:
            if dep not in story_numbers:
                failures.append(
                    f"Story #{story['number']} depends on #{dep} which does not exist"
                )

    # Check for circular dependencies using DFS
    adj = {s["number"]: s["depends"] for s in stories}
    visited = set()
    in_stack = set()

    def has_cycle(node: int) -> bool:
        if node in in_stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        in_stack.add(node)
        for dep in adj.get(node, []):
            if has_cycle(dep):
                return True
        in_stack.discard(node)
        return False

    for s in stories:
        if has_cycle(s["number"]):
            failures.append("Circular dependency detected in the story dependency graph")
            break

    # Warn if story #1 has dependencies
    if stories and stories[0]["depends"]:
        failures.append(
            f"Story #1 depends on {stories[0]['depends']} — scaffolding "
            "should have no dependencies"
        )

    return failures


def check_prohibited_content(stories: list[dict]) -> list[str]:
    """A3: Check for test, container, and pre-planned refactoring stories.

    Returns a list of failure messages (fixable items). Empty list = pass.
    """
    failures = []
    for story in stories:
        name = story["name"]
        if _TEST_KEYWORDS.search(name):
            failures.append(
                f"Story #{story['number']} ('{name}') is a test story — "
                "remove it (tester agent handles testing)"
            )
        if _CONTAINER_KEYWORDS.search(name):
            failures.append(
                f"Story #{story['number']} ('{name}') is a container/deployment story — "
                "remove it (validator agent handles containerization)"
            )
        if _REFACTOR_KEYWORDS.search(name):
            failures.append(
                f"Story #{story['number']} ('{name}') is a pre-planned refactoring story — "
                "remove it (cleanup is handled reactively via review findings)"
            )

    return failures


def check_first_milestone(tasks_text: str) -> list[str]:
    """A4: Validate the first milestone structure.

    Accepts the text content of a single milestone file (from milestones/)
    or legacy TASKS.md content. Returns a list of failure messages.
    Empty list = pass.
    """
    failures = []
    milestones = parse_milestones_from_text(tasks_text)

    if len(milestones) == 0:
        failures.append("No milestone headings found in milestone file")
        return failures

    if len(milestones) > 1:
        failures.append(
            f"Milestone file contains {len(milestones)} milestones — "
            "backlog planner should create exactly one per file"
        )

    first = milestones[0]

    # Check for Validates block
    validates_found = False
    in_first_milestone = False
    for line in tasks_text.split("\n"):
        if re.match(r"^##\s+Milestone:", line, re.IGNORECASE):
            if not in_first_milestone:
                in_first_milestone = True
                continue
            else:
                break  # second milestone — stop
        if in_first_milestone and re.match(r"^>\s*\*\*Validates", line):
            validates_found = True
            break

    if not validates_found:
        failures.append(
            "First milestone is missing a '> **Validates:**' block — "
            "the validator needs acceptance criteria"
        )

    # Check task count
    task_count = first["total"]
    if task_count == 0:
        failures.append("First milestone has no tasks")
    elif task_count > 10:
        failures.append(
            f"First milestone has {task_count} tasks (max 10) — split it"
        )
    elif task_count > 7:
        failures.append(
            f"First milestone has {task_count} tasks (preferred max 7) — "
            "consider splitting"
        )

    return failures


def estimate_feature_count(requirements_text: str) -> int:
    """B: Estimate the number of distinct features from REQUIREMENTS.md.

    Counts ## and ### headings as a rough feature proxy, plus entity names,
    endpoint paths, and page references as supporting signals. Returns the
    higher of heading count and entity/endpoint/page count.
    """
    heading_count = len(_HEADING_RE.findall(requirements_text))
    entities = set(_ENTITY_RE.findall(requirements_text))
    endpoints = set(_ENDPOINT_RE.findall(requirements_text))
    pages = set(_PAGE_RE.findall(requirements_text))
    artifact_count = len(entities) + len(endpoints) + len(pages)

    # Use headings as primary proxy, artifact count as floor
    return max(heading_count, artifact_count // 3, 1)


def check_proportionality(story_count: int, feature_count: int) -> str | None:
    """B: Check if story count is proportional to estimated feature count.

    Returns a failure/warning message or None if pass.
    Ratio thresholds: < 0.5 or > 4.0 = fail; 0.5-0.99 or 3.1-4.0 = warn.
    """
    if feature_count == 0:
        return None

    ratio = story_count / feature_count
    if ratio < 0.5:
        return (
            f"Story count ({story_count}) is very low for estimated features "
            f"({feature_count}). Ratio {ratio:.1f} — stories may be too coarse "
            "or features are under-decomposed"
        )
    if ratio > 4.0:
        return (
            f"Story count ({story_count}) is very high for estimated features "
            f"({feature_count}). Ratio {ratio:.1f} — stories may be over-split"
        )
    if ratio < 1.0:
        return (
            f"Story/feature ratio is {ratio:.1f} ({story_count} stories / "
            f"{feature_count} features) — stories may be slightly coarse"
        )
    if ratio > 3.0:
        return (
            f"Story/feature ratio is {ratio:.1f} ({story_count} stories / "
            f"{feature_count} features) — stories may be slightly over-split"
        )
    return None


def check_story_ordering(stories: list[dict]) -> list[str]:
    """Check that stories appear in topological dependency order.

    A story is misordered if it appears after stories that don't depend on it
    but have lower dependency depth. Specifically: a story's position should be
    close to max(position of its dependencies) + 1.

    Returns a list of warning messages for misordered stories. Empty = pass.
    """
    if len(stories) <= 1:
        return []

    warnings = []
    number_to_pos = {s["number"]: i for i, s in enumerate(stories)}

    for story in stories:
        if not story["depends"]:
            # Stories with no deps should be near the top (after story #1)
            # Only flag if they appear after position 10 and they're not story #1
            if story["number"] != stories[0]["number"] and number_to_pos[story["number"]] > 10:
                warnings.append(
                    f"Story #{story['number']} ('{story['name']}') has no dependencies "
                    f"but appears at position {number_to_pos[story['number']] + 1} — "
                    "should appear earlier"
                )
            continue

        # Find the latest dependency position
        dep_positions = []
        for dep in story["depends"]:
            if dep in number_to_pos:
                dep_positions.append(number_to_pos[dep])

        if not dep_positions:
            continue

        latest_dep_pos = max(dep_positions)
        story_pos = number_to_pos[story["number"]]
        gap = story_pos - latest_dep_pos

        # A story should appear soon after its last dependency.
        # Gap > 10 means there are 10+ unrelated stories between a dependency
        # and the story that needs it.
        if gap > 10:
            latest_dep_number = None
            for s in stories:
                if number_to_pos[s["number"]] == latest_dep_pos:
                    latest_dep_number = s["number"]
                    break
            warnings.append(
                f"Story #{story['number']} ('{story['name']}') depends on "
                f"#{latest_dep_number} (position {latest_dep_pos + 1}) but appears "
                f"at position {story_pos + 1} — gap of {gap} stories"
            )

    return warnings


# ============================================
# Orchestration: run all deterministic checks
# ============================================

_ACTION_REPLAN = "re-plan"
_ACTION_FIX = "fix"
_ACTION_WARN = "warn"


def run_deterministic_checks(
    backlog_text: str,
    tasks_text: str,
    requirements_text: str,
) -> tuple[list[str], list[str], list[str]]:
    """Run all deterministic checks (A1-A4, B) against planner output.

    Pure function: takes file contents, returns categorized issues.

    Returns:
        (replan_failures, fix_failures, warnings)
        - replan_failures: issues that require a full re-plan
        - fix_failures: issues that can be fixed by targeted edits
        - warnings: non-blocking issues logged for visibility
    """
    replan = []
    fix = []
    warnings = []

    stories = parse_backlog(backlog_text)

    # A1: Heading check (warn only)
    heading_issue = check_backlog_heading(backlog_text)
    if heading_issue:
        warnings.append(heading_issue)

    # A1: Story format
    format_issues = check_story_format(stories, backlog_text)
    for issue in format_issues:
        # Missing depends annotation and unchecked first story are re-plan triggers
        if "not checked" in issue or "missing" in issue.lower():
            replan.append(issue)
        else:
            warnings.append(issue)

    # A2: Dependency graph
    dep_issues = check_dependency_graph(stories)
    for issue in dep_issues:
        if "does not exist" in issue or "Circular" in issue:
            replan.append(issue)
        else:
            warnings.append(issue)

    # A3: Prohibited content
    prohibited = check_prohibited_content(stories)
    for issue in prohibited:
        fix.append(issue)

    # A4: First milestone
    milestone_issues = check_first_milestone(tasks_text)
    for issue in milestone_issues:
        if "no milestone" in issue.lower() or "no tasks" in issue.lower():
            replan.append(issue)
        elif "missing" in issue.lower() and "Validates" in issue:
            replan.append(issue)
        elif "max 10" in issue:
            replan.append(issue)
        else:
            warnings.append(issue)

    # B: Proportionality
    story_count = len(stories)
    feature_count = estimate_feature_count(requirements_text)
    prop_issue = check_proportionality(story_count, feature_count)
    if prop_issue:
        if "very low" in prop_issue or "very high" in prop_issue:
            replan.append(prop_issue)
        else:
            warnings.append(prop_issue)

    return replan, fix, warnings


# ============================================
# LLM quality check (C1-C7)
# ============================================


def run_quality_check(deterministic_warnings: list[str]) -> bool:
    """Run the LLM quality check (C1-C7) via a single Copilot call.

    Called after deterministic checks pass. The LLM evaluates story quality,
    ordering, specificity, and coverage. If issues are found, the LLM fixes
    them directly (same as completeness check pattern).

    Args:
        deterministic_warnings: non-blocking warnings from deterministic checks,
            included in the prompt so the LLM has full context.

    Returns True if the quality check Copilot call succeeded, False if it failed.
    """
    warning_context = ""
    if deterministic_warnings:
        warning_block = "\n".join(f"- {w}" for w in deterministic_warnings)
        warning_context = (
            f"\n\nDeterministic checks also flagged these warnings (non-blocking, "
            f"but fix them if you agree they are real issues):\n{warning_block}"
        )

    prompt = BACKLOG_QUALITY_PROMPT + warning_context

    log("planner", "")
    log("planner", "[Backlog Checker] Running story quality check...", style="magenta")
    exit_code = run_copilot("planner", prompt)
    if exit_code != 0:
        log(
            "planner",
            "[Backlog Checker] WARNING: Quality check failed. Continuing with existing backlog.",
            style="bold yellow",
        )
        return False
    return True


# ============================================
# Top-level entry point
# ============================================


def check_backlog_quality() -> bool:
    """Run the full backlog quality check pipeline.

    Reads BACKLOG.md, milestone files from milestones/, and REQUIREMENTS.md
    from the current directory. Runs deterministic checks first, then LLM
    quality check if deterministic checks pass.

    Returns True if the backlog passed (or was fixed), False if a re-plan is needed.
    """
    # Read files
    backlog_text = _read_file_safe("BACKLOG.md")
    requirements_text = _read_file_safe("REQUIREMENTS.md")

    # Read first milestone file from milestones/ directory
    milestone_files = list_milestone_files("milestones")
    if milestone_files:
        tasks_text = _read_file_safe(milestone_files[0])
    else:
        tasks_text = ""

    if not backlog_text:
        log("planner", "[Backlog Checker] BACKLOG.md not found or empty — skipping checks.", style="yellow")
        return True

    if not tasks_text:
        log("planner", "[Backlog Checker] No milestone files found in milestones/ — skipping checks.", style="yellow")
        return True

    # Run deterministic checks
    log("planner", "")
    log("planner", "[Backlog Checker] Running structural checks...", style="magenta")
    replan, fix, warnings = run_deterministic_checks(backlog_text, tasks_text, requirements_text)

    # Log warnings
    for w in warnings:
        log("planner", f"  [warn] {w}", style="yellow")

    # Re-plan failures are blocking
    if replan:
        for f in replan:
            log("planner", f"  [FAIL] {f}", style="bold red")
        log(
            "planner",
            f"[Backlog Checker] {len(replan)} structural issue(s) require re-planning.",
            style="bold red",
        )
        return False

    # Fix failures: log them but include in LLM prompt for correction
    for f_item in fix:
        log("planner", f"  [fix] {f_item}", style="yellow")

    all_issues = fix + warnings

    # LLM quality check
    run_quality_check(all_issues)

    log("planner", "")
    log("planner", "[Backlog Checker] Quality check complete.", style="magenta")
    return True


def _read_file_safe(path: str) -> str:
    """Read a file's contents, returning empty string on any error."""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return ""


def run_ordering_check() -> bool:
    """Run the story ordering check and fix via LLM if needed.

    Reads BACKLOG.md, detects misordered stories using the dependency graph,
    and invokes a Copilot call to reorder if any are found.

    Returns True if ordering is correct or was fixed, False on failure.
    """
    backlog_text = _read_file_safe("BACKLOG.md")
    if not backlog_text:
        return True

    stories = parse_backlog(backlog_text)
    if not stories:
        return True

    ordering_issues = check_story_ordering(stories)
    if not ordering_issues:
        log("planner", "")
        log("planner", "[Backlog Checker] Story ordering OK.", style="magenta")
        return True

    log("planner", "")
    log("planner", "[Backlog Checker] Running story ordering check...", style="magenta")
    for issue in ordering_issues:
        log("planner", f"  [order] {issue}", style="yellow")

    issue_block = "\n".join(f"- {issue}" for issue in ordering_issues)
    prompt = (
        BACKLOG_ORDERING_PROMPT
        + f"\n\nThe following stories were detected as misordered:\n{issue_block}"
    )

    exit_code = run_copilot("planner", prompt)
    if exit_code != 0:
        log(
            "planner",
            "[Backlog Checker] WARNING: Ordering fix failed. Continuing with existing order.",
            style="bold yellow",
        )
        return False

    log("planner", "[Backlog Checker] Story ordering fixed.", style="magenta")
    return True
