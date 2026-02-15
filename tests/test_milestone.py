"""Tests for milestone parsing, boundary tracking, and progress helpers."""

from agent.milestone import (
    count_unstarted_milestones,
    get_next_eligible_story,
    has_pending_backlog_stories,
    has_unexpanded_stories,
    parse_backlog,
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


def test_back_to_back_milestone_headings_skips_empty_one():
    content = (
        "## Milestone: Empty milestone\n"
        "## Milestone: Real milestone\n"
        "- [ ] Do something\n"
        "- [x] Already done\n"
    )
    result = parse_milestones_from_text(content)
    assert len(result) == 1
    assert result[0] == {"name": "Real milestone", "done": 1, "total": 2}


# ---- Fixture for new roadmap-format TASKS.md ----

REALISTIC_TASKS_MD_WITH_ROADMAP = """\
# Task Plan

## Roadmap
1. ~~Backend scaffolding~~ ✓
2. ~~Members~~ ✓
3. Program years and projects
4. Events and attendance
5. Auditions

## Milestone: Backend scaffolding
- [x] Create solution with Domain, Application, Infrastructure, Api projects
- [x] Configure Program.cs with health endpoint and OpenAPI/Swagger
- [x] Add EF Core in-memory database with empty DbContext

## Milestone: Members — domain and data
- [x] Create Organization entity (Id, Name)
- [x] Create Member entity (Id, FirstName, LastName, Email, Role enum, IsActive)
- [x] Add Fluent API configuration and seed data

## Milestone: Members — API and frontend
- [x] Create MemberRepository and MemberService
- [x] Create MembersController with CRUD endpoints
- [x] Create Members list page and detail page

## Milestone: Program years — backend
- [ ] Create ProgramYear entity (Id, Name, StartDate, EndDate, IsCurrent)
- [ ] Create Project entity (Id, Name, Description, ProgramYearId)
- [ ] Create repositories inheriting BaseRepository<T> pattern
- [ ] Create ProgramYearService, ProjectService, and controllers

## Milestone: Program years — frontend
- [ ] Create Program Years list page
- [ ] Create Project detail page with assignment panel
"""


# ---- Tests for has_unexpanded_stories ----

def test_has_unexpanded_stories_mixed():
    content = "## Roadmap\n1. ~~Backend scaffolding~~ ✓\n2. Members\n3. Projects\n"
    assert has_unexpanded_stories(content) is True


def test_has_unexpanded_stories_all_done():
    content = "## Roadmap\n1. ~~Backend scaffolding~~ ✓\n2. ~~Members~~ ✓\n"
    assert has_unexpanded_stories(content) is False


def test_has_unexpanded_stories_no_roadmap():
    content = "## Milestone: Setup\n- [ ] Create project\n"
    assert has_unexpanded_stories(content) is False


def test_has_unexpanded_stories_empty():
    assert has_unexpanded_stories("") is False


def test_has_unexpanded_stories_old_format_no_roadmap():
    """Backward compat: old-format TASKS.md (all milestones upfront, no roadmap) returns False."""
    assert has_unexpanded_stories(REALISTIC_TASKS_MD) is False


def test_has_unexpanded_stories_with_full_roadmap():
    """The realistic roadmap fixture has 3 unexpanded stories."""
    assert has_unexpanded_stories(REALISTIC_TASKS_MD_WITH_ROADMAP) is True


# ---- Tests for count_unstarted_milestones ----

def test_count_unstarted_milestones_mixed():
    content = (
        "## Milestone: Done\n- [x] Task 1\n"
        "## Milestone: In Progress\n- [x] Task 1\n- [ ] Task 2\n"
        "## Milestone: Not Started\n- [ ] Task 1\n"
    )
    assert count_unstarted_milestones(content) == 1


def test_count_unstarted_milestones_all_done():
    content = "## Milestone: Done\n- [x] Task 1\n"
    assert count_unstarted_milestones(content) == 0


def test_count_unstarted_milestones_with_roadmap_fixture():
    """Two fully unstarted milestones in the roadmap fixture."""
    assert count_unstarted_milestones(REALISTIC_TASKS_MD_WITH_ROADMAP) == 2


# ---- Backward compatibility: existing parser ignores roadmap ----

def test_parse_milestones_ignores_roadmap_section():
    content = (
        "## Roadmap\n1. Backend scaffolding\n2. Members\n\n"
        "## Milestone: Setup\n- [ ] Create project\n- [x] Add config\n"
    )
    milestones = parse_milestones_from_text(content)
    assert len(milestones) == 1
    assert milestones[0]["name"] == "Setup"
    assert milestones[0]["total"] == 2


def test_existing_parser_works_with_roadmap_fixture():
    """Existing parse_milestones_from_text returns only ## Milestone: headings from new format."""
    milestones = parse_milestones_from_text(REALISTIC_TASKS_MD_WITH_ROADMAP)
    assert len(milestones) == 5
    assert milestones[0] == {"name": "Backend scaffolding", "done": 3, "total": 3}
    assert milestones[4] == {"name": "Program years — frontend", "done": 0, "total": 2}


def test_existing_parser_still_works_with_old_format():
    """Confirm existing REALISTIC_TASKS_MD fixture still parses correctly."""
    result = parse_milestones_from_text(REALISTIC_TASKS_MD)
    assert len(result) == 3
    assert result[0] == {"name": "Project scaffolding", "done": 3, "total": 4}


# ============================================
# Backlog parsing tests
# ============================================

SAMPLE_BACKLOG = """\
# Backlog

1. [x] Project scaffolding and base configuration
2. [x] Books CRUD <!-- depends: 1 -->
3. [ ] Authors CRUD <!-- depends: 1 -->
4. [ ] Search <!-- depends: 2, 3 -->
5. [ ] Reviews <!-- depends: 2 -->
"""

SAMPLE_BACKLOG_ALL_DONE = """\
# Backlog

1. [x] Project scaffolding and base configuration
2. [x] Books CRUD <!-- depends: 1 -->
3. [x] Authors CRUD <!-- depends: 1 -->
"""

SAMPLE_BACKLOG_DEADLOCK = """\
# Backlog

1. [x] Scaffolding
2. [ ] Feature A <!-- depends: 3 -->
3. [ ] Feature B <!-- depends: 2 -->
"""


def test_parse_backlog_basic():
    stories = parse_backlog(SAMPLE_BACKLOG)
    assert len(stories) == 5
    assert stories[0] == {"number": 1, "name": "Project scaffolding and base configuration", "checked": True, "depends": []}
    assert stories[1] == {"number": 2, "name": "Books CRUD", "checked": True, "depends": [1]}
    assert stories[3] == {"number": 4, "name": "Search", "checked": False, "depends": [2, 3]}


def test_parse_backlog_empty():
    assert parse_backlog("") == []
    assert parse_backlog("# Backlog\n\nSome random text\n") == []


def test_has_pending_backlog_stories_mixed():
    assert has_pending_backlog_stories(SAMPLE_BACKLOG) is True


def test_has_pending_backlog_stories_all_done():
    assert has_pending_backlog_stories(SAMPLE_BACKLOG_ALL_DONE) is False


def test_has_pending_backlog_stories_empty():
    assert has_pending_backlog_stories("") is False


def test_get_next_eligible_story_skips_unmet_deps():
    """Story 4 (Search) depends on 2 and 3, but 3 is unchecked. Should pick story 3 (Authors)."""
    story = get_next_eligible_story(SAMPLE_BACKLOG)
    assert story is not None
    assert story["name"] == "Authors CRUD"
    assert story["number"] == 3


def test_get_next_eligible_story_picks_first_eligible():
    """Among eligible stories 3 (Authors) and 5 (Reviews), picks 3 first."""
    story = get_next_eligible_story(SAMPLE_BACKLOG)
    assert story["number"] == 3


def test_get_next_eligible_story_all_done():
    story = get_next_eligible_story(SAMPLE_BACKLOG_ALL_DONE)
    assert story is None


def test_get_next_eligible_story_deadlock():
    """Stories 2 and 3 depend on each other — no eligible story despite pending work."""
    story = get_next_eligible_story(SAMPLE_BACKLOG_DEADLOCK)
    assert story is None
    assert has_pending_backlog_stories(SAMPLE_BACKLOG_DEADLOCK) is True
