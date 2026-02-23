"""Tests for backlog_checker: deterministic checks against real and synthetic backlogs."""

from agentic_dev.backlog_checker import (
    check_backlog_heading,
    check_dependency_graph,
    check_first_milestone,
    check_prohibited_content,
    check_proportionality,
    check_story_format,
    check_story_ordering,
    estimate_feature_count,
    run_deterministic_checks,
)
from agentic_dev.milestone import parse_backlog


# ============================================
# Real backlog fixtures from harness runs
# ============================================

STRETTO_BACKLOG = """\
# Stretto — Backlog

1. [x] Scaffolding — .NET solution with Domain/Application/Infrastructure/Api projects, React app with Vite, health endpoint, OpenAPI/Swagger, dotnet format and ESLint/Prettier configs <!-- depends: none -->
2. [x] Database & tenant foundation — EF Core in-memory DbContext, Organization entity with Fluent API config, global query filter for OrganizationId tenant scoping <!-- depends: 1 -->
3. [x] Authentication & session — Member entity (Id, Name, Email, OrganizationId, Role, IsActive), passwordless email-only login endpoint <!-- depends: 2 -->
4. [x] API client generation — Configure OpenAPI TypeScript client generation <!-- depends: 1 -->
5. [x] Frontend app shell & navigation — Login page consuming auth API, React Router route structure <!-- depends: 3, 4 -->
6. [x] Members — backend API — Member repository and service, CRUD endpoints <!-- depends: 3 -->
7. [x] Members — admin pages — Members list page with search/filter, add member form <!-- depends: 5, 6 -->
8. [x] Program years — backend API — ProgramYear entity, repository, service, CRUD endpoints <!-- depends: 3 -->
9. [x] Program years — admin pages — Program years list, create/edit form <!-- depends: 5, 8 -->
10. [x] Projects — backend API — Project entity, repository, service, CRUD endpoints <!-- depends: 8 -->
"""

BOOKSTORE_CLAUDE_BACKLOG = """\
# Backlog

1. [x] Project scaffolding — Create .NET 10 minimal API backend project and React 19 + Vite + TypeScript frontend project with entry points and health endpoint <!-- depends: none -->
2. [x] Book entity and repository — Define Book model (Id, Title, Author, ISBN, Price, Genre) and thread-safe in-memory repository <!-- depends: 1 -->
3. [x] Book read endpoints and seed data — GET /books (200) and GET /books/{id} (200 or 404), CORS configuration, seed 2-3 sample books <!-- depends: 2 -->
4. [x] Book write endpoints with validation — POST /books (201), PUT /books/{id} (200 or 404), DELETE /books/{id} (204 or 404) <!-- depends: 3 -->
5. [x] Frontend API client — Create API client module encapsulating all HTTP calls <!-- depends: 1 -->
6. [x] Book list view — Main page displaying all books in a responsive table <!-- depends: 5, 3 -->
7. [x] Add and edit book form — Form component with validation <!-- depends: 6, 4 -->
8. [x] Delete book and error handling — Delete button with confirmation prompt, error messages <!-- depends: 7 -->
"""

BOOKSTORE_CODEX_BACKLOG = """\
1. [x] Scaffolding baseline — create backend and frontend projects, wire startup entry points, add GET /health endpoint <!-- depends: none -->
2. [x] Books domain core — implement Book model, repository interface, in-memory repository, startup seed <!-- depends: 1 -->
3. [x] Books read API slice — add GET /books and GET /books/{id} endpoints <!-- depends: 2 -->
4. [x] Books create API slice — add POST /books endpoint with validation <!-- depends: 3 -->
5. [x] Books update-delete API slice — add PUT /books/{id} and DELETE /books/{id} <!-- depends: 4 -->
6. [x] Frontend app shell slice — initialize SPA layout, configure API base URL <!-- depends: 1, 5 -->
7. [x] Book list UI slice — render responsive Book List view <!-- depends: 6 -->
8. [x] Add or edit form UI slice — implement Add or Edit book form <!-- depends: 7 -->
9. [x] Delete interaction slice — add delete action with confirmation prompt <!-- depends: 7 -->
10. [x] Development integration hardening — enable CORS, finalize error mapping <!-- depends: 5, 9 -->
11. [x] Code formatting enforcement setup — add formatting commands/config <!-- depends: 1 -->
12. [x] Frontend orchestration cleanup slice — split oversized App orchestration into hooks <!-- depends: 10 -->
"""


# ============================================
# A1: Heading check
# ============================================


def test_heading_present():
    assert check_backlog_heading(STRETTO_BACKLOG) is None


def test_heading_present_simple():
    assert check_backlog_heading(BOOKSTORE_CLAUDE_BACKLOG) is None


def test_heading_missing():
    result = check_backlog_heading(BOOKSTORE_CODEX_BACKLOG)
    assert result is not None
    assert "heading" in result.lower()


def test_heading_wrong_format():
    result = check_backlog_heading("## Not a top-level heading\n1. [x] Story <!-- depends: none -->")
    assert result is not None


# ============================================
# A1: Story format
# ============================================


def test_story_format_stretto_passes():
    stories = parse_backlog(STRETTO_BACKLOG)
    issues = check_story_format(stories, STRETTO_BACKLOG)
    # All checked, sequential, all have depends
    assert len(issues) == 0


def test_story_format_bookstore_claude_passes():
    stories = parse_backlog(BOOKSTORE_CLAUDE_BACKLOG)
    issues = check_story_format(stories, BOOKSTORE_CLAUDE_BACKLOG)
    assert len(issues) == 0


def test_story_format_first_unchecked_no_issue():
    """Unchecked story #1 is not flagged — the orchestration handles it after milestone planning."""
    backlog = "# Backlog\n1. [ ] Story one <!-- depends: none -->\n2. [ ] Story two <!-- depends: 1 -->"
    stories = parse_backlog(backlog)
    issues = check_story_format(stories, backlog)
    assert not any("not checked" in i for i in issues)


def test_story_format_missing_depends():
    backlog = "# Backlog\n1. [x] Story one\n2. [ ] Story two <!-- depends: 1 -->"
    stories = parse_backlog(backlog)
    issues = check_story_format(stories, backlog)
    assert any("missing" in i.lower() and "depends" in i.lower() for i in issues)


def test_story_format_empty():
    stories = parse_backlog("")
    issues = check_story_format(stories, "")
    assert any("no parseable" in i.lower() for i in issues)


def test_story_format_nonsequential():
    backlog = "# Backlog\n1. [x] A <!-- depends: none -->\n3. [ ] B <!-- depends: 1 -->"
    stories = parse_backlog(backlog)
    issues = check_story_format(stories, backlog)
    assert any("sequential" in i.lower() for i in issues)


# ============================================
# A2: Dependency graph
# ============================================


def test_deps_stretto_passes():
    stories = parse_backlog(STRETTO_BACKLOG)
    issues = check_dependency_graph(stories)
    assert len(issues) == 0


def test_deps_invalid_reference():
    backlog = "# Backlog\n1. [x] A <!-- depends: none -->\n2. [ ] B <!-- depends: 99 -->"
    stories = parse_backlog(backlog)
    issues = check_dependency_graph(stories)
    assert any("does not exist" in i for i in issues)


def test_deps_circular():
    backlog = (
        "# Backlog\n"
        "1. [x] A <!-- depends: 2 -->\n"
        "2. [ ] B <!-- depends: 1 -->"
    )
    stories = parse_backlog(backlog)
    issues = check_dependency_graph(stories)
    assert any("Circular" in i for i in issues)


def test_deps_story_one_has_deps():
    backlog = "# Backlog\n1. [x] A <!-- depends: 2 -->\n2. [ ] B <!-- depends: none -->"
    stories = parse_backlog(backlog)
    issues = check_dependency_graph(stories)
    assert any("scaffolding" in i.lower() for i in issues)


# ============================================
# A3: Prohibited content
# ============================================


def test_prohibited_clean():
    stories = parse_backlog(BOOKSTORE_CLAUDE_BACKLOG)
    issues = check_prohibited_content(stories)
    assert len(issues) == 0


def test_prohibited_test_story():
    backlog = "1. [x] Scaffolding <!-- depends: none -->\n2. [ ] Write unit tests for all services <!-- depends: 1 -->"
    stories = parse_backlog(backlog)
    issues = check_prohibited_content(stories)
    assert any("test story" in i.lower() for i in issues)


def test_prohibited_docker_story():
    backlog = "1. [x] Scaffolding <!-- depends: none -->\n2. [ ] Add Dockerfile and docker-compose <!-- depends: 1 -->"
    stories = parse_backlog(backlog)
    issues = check_prohibited_content(stories)
    assert any("container" in i.lower() for i in issues)


def test_prohibited_refactoring_story():
    stories = parse_backlog(BOOKSTORE_CODEX_BACKLOG)
    issues = check_prohibited_content(stories)
    assert any("refactoring" in i.lower() or "cleanup" in i.lower() for i in issues)


def test_prohibited_incidental_mention_ok():
    """A story mentioning 'test' incidentally (not as primary activity) should pass."""
    backlog = "1. [x] Create health endpoint so the validator can test it <!-- depends: none -->"
    stories = parse_backlog(backlog)
    # "test" appears but "Create health endpoint" is the primary activity
    # Our regex looks for specific test-related phrases, not bare "test"
    issues = check_prohibited_content(stories)
    assert len(issues) == 0


# ============================================
# A4: First milestone
# ============================================


def test_milestone_single_valid():
    tasks = (
        "## Milestone: Scaffolding\n"
        "> **Validates:** GET /health returns 200. `dotnet build` succeeds.\n\n"
        "- [ ] Create solution structure\n"
        "- [ ] Add health endpoint\n"
        "- [ ] Configure build\n"
    )
    issues = check_first_milestone(tasks)
    assert len(issues) == 0


def test_milestone_missing_validates():
    tasks = (
        "## Milestone: Scaffolding\n\n"
        "- [ ] Create solution structure\n"
        "- [ ] Add health endpoint\n"
        "- [ ] Configure build\n"
    )
    issues = check_first_milestone(tasks)
    assert any("Validates" in i for i in issues)


def test_milestone_zero():
    issues = check_first_milestone("# Tasks\n\nNothing here yet.")
    assert any("no milestone" in i.lower() for i in issues)


def test_milestone_two():
    tasks = (
        "## Milestone: One\n"
        "> **Validates:** stuff\n\n"
        "- [ ] Task A\n\n"
        "## Milestone: Two\n"
        "> **Validates:** more stuff\n\n"
        "- [ ] Task B\n"
    )
    issues = check_first_milestone(tasks)
    assert any("2 milestones" in i for i in issues)


def test_milestone_too_many_tasks():
    task_lines = "\n".join(f"- [ ] Task {i}" for i in range(9))
    tasks = f"## Milestone: Big\n> **Validates:** stuff\n\n{task_lines}\n"
    issues = check_first_milestone(tasks)
    assert any("max 7" in i for i in issues)


# ============================================
# B: Proportionality
# ============================================


def test_proportionality_pass():
    """8 stories / 5 features = 1.6 ratio — should pass."""
    result = check_proportionality(8, 5)
    assert result is None


def test_proportionality_too_low():
    """2 stories / 10 features = 0.2 ratio — should fail."""
    result = check_proportionality(2, 10)
    assert result is not None
    assert "very low" in result


def test_proportionality_too_high():
    """50 stories / 5 features = 10.0 ratio — should fail."""
    result = check_proportionality(50, 5)
    assert result is not None
    assert "very high" in result


def test_proportionality_slightly_low():
    """3 stories / 5 features = 0.6 ratio — warning."""
    result = check_proportionality(3, 5)
    assert result is not None
    assert "coarse" in result


def test_proportionality_slightly_high():
    """16 stories / 5 features = 3.2 ratio — warning."""
    result = check_proportionality(16, 5)
    assert result is not None
    assert "over-split" in result


def test_proportionality_zero_features():
    """Zero features — skip."""
    result = check_proportionality(5, 0)
    assert result is None


# ============================================
# B: Feature estimation
# ============================================


def test_estimate_simple_requirements():
    reqs = """\
## Books
Create Book entity.
## Authors
Create Author entity.
## Categories
Create Category entity.
"""
    count = estimate_feature_count(reqs)
    assert count >= 3


def test_estimate_complex_requirements():
    reqs = """\
## Members
Create Member entity with CRUD.
### Member attributes
Email, Name, Role.
## Events
Create Event entity.
### Event types
Rehearsal, Performance.
## Venues
Create Venue entity.
## Attendance
### Check-in
QR code check-in.
### Excused absences
Members can mark excused.
## Auditions
### Scheduling
Create audition dates.
### Sign-up
Members sign up for slots.
"""
    count = estimate_feature_count(reqs)
    assert count >= 5


# ============================================
# Full deterministic pipeline
# ============================================


SIMPLE_TASKS = (
    "## Milestone: Scaffolding\n"
    "> **Validates:** GET /health returns 200 with JSON body. `dotnet build` succeeds. `npm run build` succeeds.\n\n"
    "- [ ] Create .NET solution structure\n"
    "- [ ] Add health endpoint\n"
    "- [ ] Scaffold React frontend\n"
    "- [ ] Configure build scripts\n"
)

SIMPLE_REQUIREMENTS = """\
## Books
Create Book entity with title, author, ISBN.
### CRUD endpoints
GET, POST, PUT, DELETE for books.
## Frontend
React single-page app listing books.
"""


def test_full_pipeline_clean():
    backlog = (
        "# Backlog\n\n"
        "1. [x] Scaffolding — .NET solution, React app, health endpoint <!-- depends: none -->\n"
        "2. [ ] Books backend — Book entity (Title, Author, ISBN), CRUD endpoints <!-- depends: 1 -->\n"
        "3. [ ] Books frontend — Book list page, add/edit form <!-- depends: 1, 2 -->\n"
    )
    replan, fix, warnings = run_deterministic_checks(backlog, SIMPLE_TASKS, SIMPLE_REQUIREMENTS)
    assert len(replan) == 0
    assert len(fix) == 0


def test_full_pipeline_no_milestone_skips_a4():
    """When no milestone file exists (empty tasks_text), A4 is skipped and backlog-only checks run."""
    backlog = (
        "# Backlog\n\n"
        "1. [ ] Scaffolding — project setup <!-- depends: none -->\n"
        "2. [ ] Books backend — CRUD endpoints <!-- depends: 1 -->\n"
    )
    replan, fix, warnings = run_deterministic_checks(backlog, "", SIMPLE_REQUIREMENTS)
    # Should NOT trigger a replan for missing milestone
    assert not any("no milestone" in r.lower() for r in replan)
    assert not any("no tasks" in r.lower() for r in replan)


def test_full_pipeline_stretto():
    """Stretto backlog should pass all deterministic checks."""
    tasks = (
        "## Milestone: Scaffolding\n"
        "> **Validates:** GET /api/health returns 200. `dotnet build` succeeds. `npm run build` succeeds.\n\n"
        "- [ ] Create .NET solution with Domain, Application, Infrastructure, Api projects\n"
        "- [ ] Add health endpoint returning JSON status\n"
        "- [ ] Scaffold React app with Vite and TypeScript\n"
        "- [ ] Configure dotnet format and ESLint/Prettier\n"
        "- [ ] Add OpenAPI/Swagger configuration\n"
    )
    replan, fix, warnings = run_deterministic_checks(STRETTO_BACKLOG, tasks, SIMPLE_REQUIREMENTS)
    assert len(replan) == 0
    assert len(fix) == 0


def test_full_pipeline_codex_catches_issues():
    """Codex bookstore has prohibited stories (refactoring, formatting)."""
    tasks = (
        "## Milestone: Scaffolding\n"
        "> **Validates:** GET /health returns 200.\n\n"
        "- [ ] Create backend project\n"
        "- [ ] Create frontend project\n"
        "- [ ] Add health endpoint\n"
    )
    replan, fix, warnings = run_deterministic_checks(BOOKSTORE_CODEX_BACKLOG, tasks, SIMPLE_REQUIREMENTS)
    # Should catch the refactoring / cleanup stories
    assert len(fix) > 0


def test_full_pipeline_missing_deps_triggers_replan():
    backlog = (
        "# Backlog\n\n"
        "1. [x] Scaffolding\n"  # missing depends annotation
        "2. [ ] Books <!-- depends: 1 -->\n"
    )
    tasks = (
        "## Milestone: Scaffolding\n"
        "> **Validates:** GET /health returns 200.\n\n"
        "- [ ] Create project\n"
        "- [ ] Add endpoint\n"
        "- [ ] Configure build\n"
    )
    replan, fix, warnings = run_deterministic_checks(backlog, tasks, SIMPLE_REQUIREMENTS)
    assert len(replan) > 0
    assert any("depends" in r.lower() for r in replan)


# ============================================
# Story ordering tests
# ============================================


def test_well_ordered_stories_pass():
    """Stories in topological order produce no warnings."""
    stories = [
        {"number": 1, "name": "Scaffolding", "checked": True, "depends": []},
        {"number": 2, "name": "Auth backend", "checked": False, "depends": [1]},
        {"number": 3, "name": "Auth frontend", "checked": False, "depends": [1, 2]},
        {"number": 4, "name": "Members backend", "checked": False, "depends": [2]},
        {"number": 5, "name": "Members frontend", "checked": False, "depends": [3, 4]},
    ]
    warnings = check_story_ordering(stories)
    assert warnings == []


def test_misordered_story_detected():
    """A story that depends only on #1 but sits at position 20+ is flagged."""
    stories = [{"number": 1, "name": "Scaffolding", "checked": True, "depends": []}]
    # Add 18 filler stories depending on previous
    for i in range(2, 20):
        stories.append({"number": i, "name": f"Story {i}", "checked": False, "depends": [i - 1]})
    # Story 20 depends only on #1 but appears last — gap of 19
    stories.append({"number": 20, "name": "Testing infra", "checked": False, "depends": [1]})
    warnings = check_story_ordering(stories)
    assert len(warnings) >= 1
    assert any("Testing infra" in w for w in warnings)


def test_no_deps_story_at_position_2_passes():
    """A no-deps story near the top doesn't get flagged."""
    stories = [
        {"number": 1, "name": "Scaffolding", "checked": True, "depends": []},
        {"number": 2, "name": "Error handling", "checked": False, "depends": []},
        {"number": 3, "name": "Auth", "checked": False, "depends": [1]},
    ]
    warnings = check_story_ordering(stories)
    assert warnings == []


def test_no_deps_story_at_end_of_long_backlog_flagged():
    """A no-deps story sitting at position 15+ is flagged."""
    stories = [{"number": 1, "name": "Scaffolding", "checked": True, "depends": []}]
    for i in range(2, 15):
        stories.append({"number": i, "name": f"Story {i}", "checked": False, "depends": [i - 1]})
    # Story 15 has no deps but appears at position 15
    stories.append({"number": 15, "name": "Shared UI components", "checked": False, "depends": []})
    warnings = check_story_ordering(stories)
    assert len(warnings) >= 1
    assert any("Shared UI" in w for w in warnings)


def test_single_story_passes():
    """Single story backlog shouldn't produce warnings."""
    stories = [{"number": 1, "name": "Scaffolding", "checked": True, "depends": []}]
    assert check_story_ordering(stories) == []


def test_empty_stories_passes():
    """Empty stories list shouldn't produce warnings."""
    assert check_story_ordering([]) == []


def test_fieldcraft_style_misordering_detected():
    """Reproduces the FieldCraft scenario: story 42 depends on #1 but sits last."""
    backlog = (
        "# FieldCraft — Backlog\n\n"
        "1. [x] Scaffolding <!-- depends: none -->\n"
    )
    for i in range(2, 42):
        backlog += f"{i}. [ ] Story {i} <!-- depends: {i - 1} -->\n"
    backlog += "42. [ ] Testing infrastructure <!-- depends: 1 -->\n"

    stories = parse_backlog(backlog)
    warnings = check_story_ordering(stories)
    assert len(warnings) >= 1
    assert any("Testing infrastructure" in w for w in warnings)
