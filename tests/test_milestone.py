"""Tests for milestone parsing, boundary tracking, and progress helpers."""

from agent.milestone import (
    parse_milestone_log,
    parse_milestones_from_text,
)


REALISTIC_TASKS_MD = """\
# Project Tasks

## Milestone: Project scaffolding
- [x] Initialize project with package.json and tsconfig
- [x] Create directory structure (src/, tests/, config/)
- [x] Add ESLint and Prettier configuration
- [ ] Remove default template code from scaffolding

## Milestone: Core data models
- [x] Define User model with validation
- [x] Define Post model with timestamps
- [ ] Add database migration scripts
- [ ] Create seed data for development

## Milestone: API endpoints
- [ ] Implement GET /users and GET /users/:id
- [ ] Implement POST /users with input validation
- [ ] Implement PUT /users/:id
- [ ] Implement DELETE /users/:id
- [ ] Add error handling middleware
"""


def test_parses_multiple_milestones_with_correct_counts():
    result = parse_milestones_from_text(REALISTIC_TASKS_MD)
    assert len(result) == 3
    assert result[0] == {"name": "Project scaffolding", "done": 3, "total": 4}
    assert result[1] == {"name": "Core data models", "done": 2, "total": 4}
    assert result[2] == {"name": "API endpoints", "done": 0, "total": 5}


def test_empty_file_returns_no_milestones():
    assert parse_milestones_from_text("") == []


def test_milestone_with_no_tasks_is_excluded():
    content = "## Milestone: Empty one\n\nJust some notes, no checkboxes.\n"
    assert parse_milestones_from_text(content) == []


def test_handles_case_insensitive_checkboxes():
    content = "## Milestone: Mixed case\n- [X] Done task\n- [x] Also done\n- [ ] Not done\n"
    result = parse_milestones_from_text(content)
    assert result[0] == {"name": "Mixed case", "done": 2, "total": 3}


def test_parses_milestone_log_with_multiple_entries():
    log_text = (
        "Project scaffolding|abc1234|def5678\n"
        "Core data models|def5678|789abcd\n"
        "API endpoints|789abcd|eee1111\n"
    )
    result = parse_milestone_log(log_text)
    assert len(result) == 3
    assert result[0] == {"name": "Project scaffolding", "start_sha": "abc1234", "end_sha": "def5678"}
    assert result[2] == {"name": "API endpoints", "start_sha": "789abcd", "end_sha": "eee1111"}


def test_milestone_log_skips_corrupted_lines():
    log_text = (
        "Good entry|aaa|bbb\n"
        "bad line with no pipes\n"
        "also|bad\n"
        "Another good|ccc|ddd\n"
    )
    result = parse_milestone_log(log_text)
    assert len(result) == 2
    assert result[0]["name"] == "Good entry"
    assert result[1]["name"] == "Another good"


def test_milestone_log_empty_text():
    assert parse_milestone_log("") == []
