"""Regression tests for prompt templates.

Every prompt template must survive a .format() call with its expected
placeholders. This catches unescaped curly braces (like {"status":"healthy"})
that would cause a KeyError at runtime.
"""

import pytest

from agentic_dev.prompts import (
    BOOTSTRAP_PROMPT,
    BUILDER_PROMPT,
    COPILOT_INSTRUCTIONS_PROMPT,
    COPILOT_INSTRUCTIONS_TEMPLATE,
    LOCAL_BOOTSTRAP_PROMPT,
    PLANNER_COMPLETENESS_PROMPT,
    PLANNER_INITIAL_PROMPT,
    PLANNER_PROMPT,
    PLANNER_SPLIT_PROMPT,
    REVIEWER_BATCH_PROMPT,
    REVIEWER_COMMIT_PROMPT,
    REVIEWER_MILESTONE_PROMPT,
    REVIEWER_PROMPT,
    TESTER_MILESTONE_PROMPT,
    TESTER_PROMPT,
    VALIDATOR_MILESTONE_PROMPT,
    VALIDATOR_PLAYWRIGHT_SECTION,
)


# Each entry: (template, kwargs needed by .format())
PROMPT_FORMAT_CASES = [
    ("BOOTSTRAP_PROMPT", BOOTSTRAP_PROMPT, {"description": "test", "gh_user": "user", "name": "proj"}),
    ("LOCAL_BOOTSTRAP_PROMPT", LOCAL_BOOTSTRAP_PROMPT, {"description": "test", "remote_path": "/tmp/repo"}),
    ("PLANNER_INITIAL_PROMPT", PLANNER_INITIAL_PROMPT, {}),
    ("PLANNER_COMPLETENESS_PROMPT", PLANNER_COMPLETENESS_PROMPT, {}),
    ("PLANNER_PROMPT", PLANNER_PROMPT, {}),
    ("PLANNER_SPLIT_PROMPT", PLANNER_SPLIT_PROMPT, {"milestone_name": "M1", "task_count": 8}),
    ("BUILDER_PROMPT", BUILDER_PROMPT, {}),
    ("REVIEWER_PROMPT", REVIEWER_PROMPT, {}),
    ("REVIEWER_COMMIT_PROMPT", REVIEWER_COMMIT_PROMPT, {"prev_sha": "aaa", "commit_sha": "bbb"}),
    ("REVIEWER_BATCH_PROMPT", REVIEWER_BATCH_PROMPT, {"commit_count": 3, "base_sha": "aaa", "head_sha": "bbb"}),
    ("REVIEWER_MILESTONE_PROMPT", REVIEWER_MILESTONE_PROMPT, {"milestone_name": "M1", "milestone_start_sha": "aaa", "milestone_end_sha": "bbb", "code_analysis_findings": "No structural issues detected."}),
    ("TESTER_PROMPT", TESTER_PROMPT, {}),
    ("TESTER_MILESTONE_PROMPT", TESTER_MILESTONE_PROMPT, {"milestone_name": "M1", "milestone_start_sha": "aaa", "milestone_end_sha": "bbb"}),
    ("VALIDATOR_MILESTONE_PROMPT", VALIDATOR_MILESTONE_PROMPT, {"milestone_name": "M1", "milestone_start_sha": "aaa", "milestone_end_sha": "bbb", "ui_testing_instructions": "", "compose_project_name": "test-proj", "app_port": 3456, "secondary_port": 3457}),
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
        ui_testing_instructions=VALIDATOR_PLAYWRIGHT_SECTION,
        compose_project_name="test-proj",
        app_port=3456,
        secondary_port=3457,
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
        ui_testing_instructions="",
        compose_project_name="test-proj",
        app_port=3456,
        secondary_port=3457,
    )
    assert "Playwright" not in result


def test_playwright_section_is_well_formed():
    """VALIDATOR_PLAYWRIGHT_SECTION is a non-empty string with key instructions."""
    assert isinstance(VALIDATOR_PLAYWRIGHT_SECTION, str)
    assert len(VALIDATOR_PLAYWRIGHT_SECTION) > 100
    assert "Playwright" in VALIDATOR_PLAYWRIGHT_SECTION
    assert "playwright.config" in VALIDATOR_PLAYWRIGHT_SECTION
    assert "data-testid" in VALIDATOR_PLAYWRIGHT_SECTION
    assert "[UI]" in VALIDATOR_PLAYWRIGHT_SECTION
