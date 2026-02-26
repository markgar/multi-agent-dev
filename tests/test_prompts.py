"""Regression tests for prompt templates.

Every prompt template must survive a .format() call with its expected
placeholders. This catches unescaped curly braces (like {"status":"healthy"})
that would cause a KeyError at runtime.
"""

import pytest

from agentic_dev.prompts import (
    BOOTSTRAP_PROMPT,
    BUILDER_FIX_ONLY_PROMPT,
    BUILDER_ISSUE_FIXING_SECTION,
    BUILDER_PROMPT,
    COPILOT_INSTRUCTIONS_PROMPT,
    COPILOT_INSTRUCTIONS_TEMPLATE,
    PLANNER_COMPLETENESS_PROMPT,
    PLANNER_INITIAL_PROMPT,
    PLANNER_JOURNEYS_PROMPT,
    PLANNER_PROMPT,
    PLANNER_SPLIT_PROMPT,
    REVIEWER_MILESTONE_PROMPT,
    TESTER_MILESTONE_PROMPT,
    VALIDATOR_JOURNEY_RESULTS_TAGS,
    VALIDATOR_JOURNEY_SECTION,
    VALIDATOR_LEGACY_RESULTS_TAGS,
    VALIDATOR_LEGACY_SCOPE,
    VALIDATOR_MILESTONE_PROMPT,
    VALIDATOR_PLAYWRIGHT_SECTION,
    VALIDATOR_PLAYWRIGHT_TRACE_SECTION,
)


# Each entry: (template, kwargs needed by .format())
PROMPT_FORMAT_CASES = [
    ("BOOTSTRAP_PROMPT", BOOTSTRAP_PROMPT, {"description": "test", "gh_user": "user", "name": "proj"}),
    ("PLANNER_INITIAL_PROMPT", PLANNER_INITIAL_PROMPT, {}),
    ("PLANNER_COMPLETENESS_PROMPT", PLANNER_COMPLETENESS_PROMPT, {}),
    ("PLANNER_PROMPT", PLANNER_PROMPT, {"story_name": "Members backend"}),
    ("PLANNER_SPLIT_PROMPT", PLANNER_SPLIT_PROMPT, {"milestone_name": "M1", "milestone_file": "milestones/milestone-01-scaffolding.md", "task_count": 8}),
    ("BUILDER_PROMPT", BUILDER_PROMPT, {"milestone_file": "milestones/milestone-01-scaffolding.md", "issue_fixing_section": BUILDER_ISSUE_FIXING_SECTION}),
    ("BUILDER_FIX_ONLY_PROMPT", BUILDER_FIX_ONLY_PROMPT, {"issue_list": "#1: Sample bug"}),
    ("REVIEWER_MILESTONE_PROMPT", REVIEWER_MILESTONE_PROMPT, {"milestone_name": "M1", "milestone_start_sha": "aaa", "milestone_end_sha": "bbb", "code_analysis_findings": "No structural issues detected.", "milestone_label": "milestone-01"}),
    ("TESTER_MILESTONE_PROMPT", TESTER_MILESTONE_PROMPT, {"milestone_name": "M1", "milestone_start_sha": "aaa", "milestone_end_sha": "bbb", "milestone_label": "milestone-01"}),
    ("PLANNER_JOURNEYS_PROMPT", PLANNER_JOURNEYS_PROMPT, {}),
    ("VALIDATOR_MILESTONE_PROMPT", VALIDATOR_MILESTONE_PROMPT, {"milestone_name": "M1", "milestone_start_sha": "aaa", "milestone_end_sha": "bbb", "validation_scope": "Test scope here.", "results_tag_instructions": "[A] tags", "ui_testing_instructions": "", "compose_project_name": "test-proj", "app_port": 3456, "secondary_port": 3457, "milestone_label": "milestone-01"}),
    ("VALIDATOR_LEGACY_SCOPE", VALIDATOR_LEGACY_SCOPE, {"milestone_name": "M1", "milestone_label": "milestone-01"}),
    ("VALIDATOR_JOURNEY_SECTION", VALIDATOR_JOURNEY_SECTION, {"journey_list": "J-1: Smoke test", "milestone_name": "M1", "milestone_label": "milestone-01"}),
    ("COPILOT_INSTRUCTIONS_TEMPLATE", COPILOT_INSTRUCTIONS_TEMPLATE, {"project_structure": "src/", "key_files": "app.py", "architecture": "monolith", "conventions": "PEP8"}),
    ("COPILOT_INSTRUCTIONS_PROMPT", COPILOT_INSTRUCTIONS_PROMPT, {"template": "...template..."}),
]


@pytest.mark.parametrize("name,template,kwargs", PROMPT_FORMAT_CASES, ids=[c[0] for c in PROMPT_FORMAT_CASES])
def test_prompt_format_does_not_raise(name, template, kwargs):
    """Calling .format() with the expected kwargs must not raise KeyError.

    This is a regression test for the bug where unescaped braces like
    {"status":"healthy"} caused a KeyError at runtime.
    """
    result = template.format(**kwargs)
    assert isinstance(result, str)
    assert len(result) > 0


def test_validator_prompt_includes_playwright_when_frontend():
    """Formatting with VALIDATOR_PLAYWRIGHT_SECTION injects Playwright instructions."""
    result = VALIDATOR_MILESTONE_PROMPT.format(
        milestone_name="UI Shell",
        milestone_start_sha="aaa",
        milestone_end_sha="bbb",
        validation_scope=VALIDATOR_LEGACY_SCOPE.format(milestone_name="UI Shell", milestone_label="milestone-01"),
        results_tag_instructions=VALIDATOR_LEGACY_RESULTS_TAGS,
        ui_testing_instructions=VALIDATOR_PLAYWRIGHT_SECTION.format(milestone_label="milestone-01"),
        compose_project_name="test-proj",
        app_port=3456,
        secondary_port=3457,
        milestone_label="milestone-01",
    )
    assert "Playwright" in result
    assert "docker" in result.lower()
    assert "data-testid" in result


def test_validator_prompt_excludes_playwright_when_no_frontend():
    """Formatting with empty ui_testing_instructions omits Playwright."""
    result = VALIDATOR_MILESTONE_PROMPT.format(
        milestone_name="API Endpoints",
        milestone_start_sha="aaa",
        milestone_end_sha="bbb",
        validation_scope=VALIDATOR_LEGACY_SCOPE.format(milestone_name="API Endpoints", milestone_label="milestone-02"),
        results_tag_instructions=VALIDATOR_LEGACY_RESULTS_TAGS,
        ui_testing_instructions="",
        compose_project_name="test-proj",
        app_port=3456,
        secondary_port=3457,
        milestone_label="milestone-02",
    )
    assert "Playwright" not in result


def test_validator_prompt_with_journey_scope():
    """Formatting with journey scope injects journey instructions."""
    journey_scope = VALIDATOR_JOURNEY_SECTION.format(journey_list="  J-1: Smoke test\n  Steps: Login and navigate\n", milestone_name="Venues", milestone_label="milestone-03")
    result = VALIDATOR_MILESTONE_PROMPT.format(
        milestone_name="Venues",
        milestone_start_sha="aaa",
        milestone_end_sha="bbb",
        validation_scope=journey_scope,
        results_tag_instructions=VALIDATOR_JOURNEY_RESULTS_TAGS,
        ui_testing_instructions="",
        compose_project_name="test-proj",
        app_port=3456,
        secondary_port=3457,
        milestone_label="milestone-03",
    )
    assert "J-1: Smoke test" in result
    assert "[J-N]" in result
    assert "three-part" not in result.lower()


def test_playwright_section_is_well_formed():
    """VALIDATOR_PLAYWRIGHT_SECTION is a non-empty string with key instructions."""
    assert isinstance(VALIDATOR_PLAYWRIGHT_SECTION, str)
    assert len(VALIDATOR_PLAYWRIGHT_SECTION) > 100
    assert "Playwright" in VALIDATOR_PLAYWRIGHT_SECTION
    assert "playwright.config" in VALIDATOR_PLAYWRIGHT_SECTION
    assert "data-testid" in VALIDATOR_PLAYWRIGHT_SECTION


def test_playwright_trace_section_is_well_formed():
    """VALIDATOR_PLAYWRIGHT_TRACE_SECTION is a non-empty string with trace instructions."""
    assert isinstance(VALIDATOR_PLAYWRIGHT_TRACE_SECTION, str)
    assert len(VALIDATOR_PLAYWRIGHT_TRACE_SECTION) > 50
    assert "trace" in VALIDATOR_PLAYWRIGHT_TRACE_SECTION.lower()
    assert "playwright-report" in VALIDATOR_PLAYWRIGHT_TRACE_SECTION


def test_playwright_trace_section_has_no_format_variables():
    """VALIDATOR_PLAYWRIGHT_TRACE_SECTION has no format placeholders."""
    result = VALIDATOR_PLAYWRIGHT_TRACE_SECTION.format()
    assert result == VALIDATOR_PLAYWRIGHT_TRACE_SECTION
    assert "[UI]" in VALIDATOR_PLAYWRIGHT_SECTION
