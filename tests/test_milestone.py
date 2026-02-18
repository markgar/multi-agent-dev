"""Tests for milestone parsing, boundary tracking, and progress helpers."""

from agentic_dev.milestone import (
    count_unstarted_milestones,
    get_all_milestones,
    get_completed_milestones_from_dir,
    get_milestone_progress_from_file,
    get_next_eligible_story,
    get_tasks_per_milestone_from_dir,
    has_pending_backlog_stories,
    has_unexpanded_stories,
    list_milestone_files,
    parse_backlog,
    parse_milestone_file,
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
    assert stories[0] == {"number": 1, "name": "Project scaffolding and base configuration", "checked": True, "status": "completed", "depends": []}
    assert stories[1] == {"number": 2, "name": "Books CRUD", "checked": True, "status": "completed", "depends": [1]}
    assert stories[3] == {"number": 4, "name": "Search", "checked": False, "status": "unclaimed", "depends": [2, 3]}


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


# ============================================
# Three-state backlog tests ([~] in-progress)
# ============================================

SAMPLE_BACKLOG_THREE_STATE = """\
# Backlog

1. [x] Project scaffolding and base configuration
2. [~] Books CRUD <!-- depends: 1 -->
3. [ ] Authors CRUD <!-- depends: 1 -->
4. [ ] Search <!-- depends: 2, 3 -->
5. [ ] Reviews <!-- depends: 2 -->
"""

SAMPLE_BACKLOG_ALL_CLAIMED = """\
# Backlog

1. [x] Scaffolding
2. [~] Feature A <!-- depends: 1 -->
3. [~] Feature B <!-- depends: 1 -->
"""


def test_parse_backlog_three_state_markers():
    """The [~] marker is parsed as in_progress with checked=True."""
    stories = parse_backlog(SAMPLE_BACKLOG_THREE_STATE)
    assert len(stories) == 5
    assert stories[0]["status"] == "completed"
    assert stories[0]["checked"] is True
    assert stories[1]["status"] == "in_progress"
    assert stories[1]["checked"] is True
    assert stories[2]["status"] == "unclaimed"
    assert stories[2]["checked"] is False


def test_in_progress_does_not_satisfy_dependencies():
    """Story 5 (Reviews) depends on story 2 which is [~]. Should NOT be eligible."""
    story = get_next_eligible_story(SAMPLE_BACKLOG_THREE_STATE)
    assert story is not None
    assert story["number"] == 3
    assert story["name"] == "Authors CRUD"


def test_in_progress_story_is_not_eligible():
    """Story 2 is [~] — it should be skipped, not returned as eligible."""
    story = get_next_eligible_story(SAMPLE_BACKLOG_THREE_STATE)
    assert story["number"] != 2


def test_all_claimed_returns_none():
    """When all uncompleted stories are [~], no eligible story exists."""
    story = get_next_eligible_story(SAMPLE_BACKLOG_ALL_CLAIMED)
    assert story is None


def test_has_pending_with_in_progress():
    """[~] stories count as checked, so unclaimed stories are still pending."""
    assert has_pending_backlog_stories(SAMPLE_BACKLOG_THREE_STATE) is True


def test_has_pending_all_claimed_or_done():
    """All stories are [x] or [~] — nothing pending."""
    assert has_pending_backlog_stories(SAMPLE_BACKLOG_ALL_CLAIMED) is False


def test_search_blocked_by_in_progress_dep():
    """Story 4 (Search) depends on 2 ([~]) and 3 ([ ]). Neither dep is completed.
    Story 5 (Reviews) depends on 2 ([~]). Not eligible.
    Only story 3 (Authors) is eligible (depends on 1 which is [x])."""
    stories = parse_backlog(SAMPLE_BACKLOG_THREE_STATE)
    completed = {s["number"] for s in stories if s["status"] == "completed"}
    assert completed == {1}
    story = get_next_eligible_story(SAMPLE_BACKLOG_THREE_STATE)
    assert story["number"] == 3


# ============================================
# Milestone file parsing tests (milestones/ directory)
# ============================================

MILESTONE_PARTIAL = """\
## Milestone: Members management

> **Validates:** GET /api/members returns 200. POST /api/members returns 201.

- [x] Create Member entity (Id, FirstName, LastName, Email, Role enum)
- [x] Create MemberRepository implementing BaseRepository<Member>
- [x] Create MemberService with CRUD operations
- [ ] Create MembersController with REST endpoints
- [ ] Add input validation for member creation
"""

MILESTONE_ALL_DONE = """\
## Milestone: Project scaffolding

> **Validates:** Health endpoint returns 200.

- [x] Initialize project with solution file
- [x] Create directory structure
- [x] Add health check endpoint
"""

MILESTONE_EMPTY = """\
## Milestone: Empty one

Just some notes but no checkbox tasks.
"""


def test_parse_milestone_file_partial(tmp_path):
    """File with 5 tasks (3 done, 2 remaining)."""
    f = tmp_path / "milestone-02-members.md"
    f.write_text(MILESTONE_PARTIAL)
    result = parse_milestone_file(str(f))
    assert result == {"name": "Members management", "done": 3, "total": 5, "all_done": False}


def test_parse_milestone_file_all_done(tmp_path):
    """File with all tasks done."""
    f = tmp_path / "milestone-01-scaffolding.md"
    f.write_text(MILESTONE_ALL_DONE)
    result = parse_milestone_file(str(f))
    assert result == {"name": "Project scaffolding", "done": 3, "total": 3, "all_done": True}


def test_parse_milestone_file_missing(tmp_path):
    """Missing file returns None."""
    result = parse_milestone_file(str(tmp_path / "nonexistent.md"))
    assert result is None


def test_parse_milestone_file_empty(tmp_path):
    """File with no checkbox tasks returns None."""
    f = tmp_path / "milestone-empty.md"
    f.write_text(MILESTONE_EMPTY)
    result = parse_milestone_file(str(f))
    assert result is None


def test_list_milestone_files_sorted(tmp_path):
    """Directory with 3 .md files — returned sorted."""
    d = tmp_path / "milestones"
    d.mkdir()
    (d / "milestone-03-api.md").write_text(MILESTONE_PARTIAL)
    (d / "milestone-01-scaffolding.md").write_text(MILESTONE_ALL_DONE)
    (d / "milestone-02-members.md").write_text(MILESTONE_PARTIAL)
    files = list_milestone_files(str(d))
    assert len(files) == 3
    assert files[0].endswith("milestone-01-scaffolding.md")
    assert files[1].endswith("milestone-02-members.md")
    assert files[2].endswith("milestone-03-api.md")


def test_list_milestone_files_missing_directory(tmp_path):
    """Missing directory returns empty list."""
    files = list_milestone_files(str(tmp_path / "nope"))
    assert files == []


def test_list_milestone_files_ignores_non_md(tmp_path):
    """Non-.md files are ignored."""
    d = tmp_path / "milestones"
    d.mkdir()
    (d / "milestone-01-scaffolding.md").write_text(MILESTONE_ALL_DONE)
    (d / "README.txt").write_text("not a milestone")
    (d / ".gitkeep").write_text("")
    files = list_milestone_files(str(d))
    assert len(files) == 1
    assert files[0].endswith(".md")


def test_get_all_milestones_mixed(tmp_path):
    """Multiple files, mixed completion."""
    d = tmp_path / "milestones"
    d.mkdir()
    (d / "milestone-01-scaffolding.md").write_text(MILESTONE_ALL_DONE)
    (d / "milestone-02-members.md").write_text(MILESTONE_PARTIAL)
    (d / "milestone-03-empty.md").write_text(MILESTONE_EMPTY)
    result = get_all_milestones(str(d))
    assert len(result) == 2  # empty file skipped
    assert result[0]["name"] == "Project scaffolding"
    assert result[0]["all_done"] is True
    assert result[1]["name"] == "Members management"
    assert result[1]["all_done"] is False


def test_get_completed_milestones_from_dir(tmp_path):
    """Filters to only completed milestones."""
    d = tmp_path / "milestones"
    d.mkdir()
    (d / "milestone-01-scaffolding.md").write_text(MILESTONE_ALL_DONE)
    (d / "milestone-02-members.md").write_text(MILESTONE_PARTIAL)
    result = get_completed_milestones_from_dir(str(d))
    assert len(result) == 1
    assert result[0] == {"name": "Project scaffolding", "all_done": True}


def test_get_milestone_progress_from_file_incomplete(tmp_path):
    """Incomplete milestone returns progress dict."""
    f = tmp_path / "milestone-02-members.md"
    f.write_text(MILESTONE_PARTIAL)
    result = get_milestone_progress_from_file(str(f))
    assert result == {"name": "Members management", "done": 3, "total": 5}


def test_get_milestone_progress_from_file_completed(tmp_path):
    """Completed milestone returns None."""
    f = tmp_path / "milestone-01-scaffolding.md"
    f.write_text(MILESTONE_ALL_DONE)
    result = get_milestone_progress_from_file(str(f))
    assert result is None


def test_get_tasks_per_milestone_from_dir(tmp_path):
    """Counts tasks for uncompleted milestones only."""
    d = tmp_path / "milestones"
    d.mkdir()
    (d / "milestone-01-scaffolding.md").write_text(MILESTONE_ALL_DONE)
    (d / "milestone-02-members.md").write_text(MILESTONE_PARTIAL)
    result = get_tasks_per_milestone_from_dir(str(d))
    assert len(result) == 1
    assert result[0] == {"name": "Members management", "task_count": 5}
