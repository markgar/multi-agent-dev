"""Tests for journey parsing, eligibility filtering, and greedy set-cover selection."""

from agentic_dev.journeys import (
    Journey,
    filter_eligible_journeys,
    format_journey_prompt_block,
    get_completed_story_numbers,
    parse_journeys,
    select_journeys,
    select_journeys_for_milestone,
)


# ============================================
# Journey parsing
# ============================================

SAMPLE_JOURNEYS = """\
# User Journeys

## J-1: Admin navigates all sidebar links
<!-- after: 3 -->
<!-- covers: navigation -->
<!-- tags: smoke -->
Login as admin → click each sidebar nav item → verify each page loads without errors

## J-2: Admin creates and edits a venue
<!-- after: 4 -->
<!-- covers: venues.crud -->
Login as admin → Venues sidebar → Create → fill name, address, contact → submit → verify in list → edit → save → verify updated

## J-7: Admin creates event at venue
<!-- after: 9 -->
<!-- covers: venues.crud, program-years.crud, projects.crud, events.crud -->
Login as admin → Venues → create venue → Program Years → create + current → Projects → create project → Project → Add Event → select venue → submit → verify event in list
"""


def test_parse_journeys_extracts_all_three():
    journeys = parse_journeys(SAMPLE_JOURNEYS)
    assert len(journeys) == 3


def test_parse_journeys_extracts_ids():
    journeys = parse_journeys(SAMPLE_JOURNEYS)
    ids = [j.id for j in journeys]
    assert ids == ["J-1", "J-2", "J-7"]


def test_parse_journeys_extracts_titles():
    journeys = parse_journeys(SAMPLE_JOURNEYS)
    assert journeys[0].title == "Admin navigates all sidebar links"
    assert journeys[1].title == "Admin creates and edits a venue"
    assert journeys[2].title == "Admin creates event at venue"


def test_parse_journeys_extracts_after():
    journeys = parse_journeys(SAMPLE_JOURNEYS)
    assert journeys[0].after == 3
    assert journeys[1].after == 4
    assert journeys[2].after == 9


def test_parse_journeys_extracts_covers():
    journeys = parse_journeys(SAMPLE_JOURNEYS)
    assert journeys[0].covers == {"navigation"}
    assert journeys[1].covers == {"venues.crud"}
    assert journeys[2].covers == {"venues.crud", "program-years.crud", "projects.crud", "events.crud"}


def test_parse_journeys_extracts_tags():
    journeys = parse_journeys(SAMPLE_JOURNEYS)
    assert journeys[0].tags == {"smoke"}
    assert journeys[1].tags == set()
    assert journeys[2].tags == set()


def test_parse_journeys_extracts_description():
    journeys = parse_journeys(SAMPLE_JOURNEYS)
    assert "sidebar nav item" in journeys[0].description
    assert "fill name, address, contact" in journeys[1].description


def test_parse_journeys_empty_content():
    assert parse_journeys("") == []


def test_parse_journeys_no_journeys():
    assert parse_journeys("# User Journeys\n\nSome intro text.\n") == []


def test_parse_journeys_skips_incomplete_journey():
    """A journey without <!-- after: --> is skipped."""
    content = """\
## J-1: Has no after
<!-- covers: navigation -->
Some description

## J-2: Has all fields
<!-- after: 1 -->
<!-- covers: auth -->
Login steps
"""
    journeys = parse_journeys(content)
    assert len(journeys) == 1
    assert journeys[0].id == "J-2"


def test_parse_journeys_skips_journey_without_covers():
    """A journey without <!-- covers: --> is skipped."""
    content = """\
## J-1: Has no covers
<!-- after: 1 -->
Some description
"""
    journeys = parse_journeys(content)
    assert len(journeys) == 0


# ============================================
# Completed story detection
# ============================================


SAMPLE_BACKLOG = """\
# Backlog

1. [x] Project scaffolding <!-- depends: none -->
2. [x] Auth — login and roles <!-- depends: 1 -->
3. [x] Navigation — sidebar layout <!-- depends: 1 -->
4. [1] Venues — CRUD backend + admin pages <!-- depends: 1 -->
5. [ ] Members — CRUD backend + admin pages <!-- depends: 1, 2 -->
6. [x] Program Years <!-- depends: 1 -->
7. [ ] Projects <!-- depends: 1, 6 -->
"""


def test_get_completed_story_numbers():
    completed = get_completed_story_numbers(SAMPLE_BACKLOG)
    assert completed == {1, 2, 3, 6}


def test_get_completed_story_numbers_empty():
    assert get_completed_story_numbers("") == set()


def test_get_completed_story_numbers_none_completed():
    content = "1. [ ] Story one <!-- depends: none -->\n2. [ ] Story two <!-- depends: 1 -->"
    assert get_completed_story_numbers(content) == set()


# ============================================
# Eligibility filtering
# ============================================


def test_filter_eligible_journeys_all_eligible():
    journeys = [
        Journey("J-1", "A", after=1, covers={"nav"}, tags=set(), description="go"),
        Journey("J-2", "B", after=2, covers={"auth"}, tags=set(), description="go"),
    ]
    eligible = filter_eligible_journeys(journeys, {1, 2, 3})
    assert len(eligible) == 2


def test_filter_eligible_journeys_partial():
    journeys = [
        Journey("J-1", "A", after=1, covers={"nav"}, tags=set(), description="go"),
        Journey("J-2", "B", after=5, covers={"auth"}, tags=set(), description="go"),
    ]
    eligible = filter_eligible_journeys(journeys, {1, 2, 3})
    assert len(eligible) == 1
    assert eligible[0].id == "J-1"


def test_filter_eligible_journeys_none_eligible():
    journeys = [
        Journey("J-1", "A", after=10, covers={"nav"}, tags=set(), description="go"),
    ]
    eligible = filter_eligible_journeys(journeys, {1, 2})
    assert len(eligible) == 0


def test_filter_eligible_journeys_empty_input():
    assert filter_eligible_journeys([], {1, 2}) == []


# ============================================
# Greedy set-cover selection
# ============================================


def test_select_journeys_picks_largest_first():
    """J-3 covers {a, b, c}, J-1 covers {a}, J-2 covers {b}. J-3 alone covers everything."""
    j1 = Journey("J-1", "A", after=1, covers={"a"}, tags=set(), description="go")
    j2 = Journey("J-2", "B", after=1, covers={"b"}, tags=set(), description="go")
    j3 = Journey("J-3", "C", after=1, covers={"a", "b", "c"}, tags=set(), description="go")
    selected = select_journeys([j1, j2, j3])
    assert len(selected) == 1
    assert selected[0].id == "J-3"


def test_select_journeys_retires_subsets():
    """J-2 covers {venues} which is a subset of J-7's {venues, projects, events}."""
    j2 = Journey("J-2", "Venues", after=4, covers={"venues"}, tags=set(), description="go")
    j7 = Journey("J-7", "Events", after=9, covers={"venues", "projects", "events"}, tags=set(), description="go")
    selected = select_journeys([j2, j7])
    assert len(selected) == 1
    assert selected[0].id == "J-7"


def test_select_journeys_needs_multiple_when_no_single_covers_all():
    j1 = Journey("J-1", "A", after=1, covers={"nav", "auth"}, tags=set(), description="go")
    j2 = Journey("J-2", "B", after=2, covers={"venues"}, tags=set(), description="go")
    selected = select_journeys([j1, j2])
    assert len(selected) == 2
    selected_ids = {j.id for j in selected}
    assert selected_ids == {"J-1", "J-2"}


def test_select_journeys_empty_list():
    assert select_journeys([]) == []


def test_select_journeys_deterministic_on_ties():
    """When two journeys cover the same number of new features, pick by ID."""
    j1 = Journey("J-1", "A", after=1, covers={"x"}, tags=set(), description="go")
    j2 = Journey("J-2", "B", after=1, covers={"y"}, tags=set(), description="go")
    selected = select_journeys([j1, j2])
    assert selected[0].id == "J-1"
    assert selected[1].id == "J-2"


def test_select_journeys_complex_overlap():
    """Three journeys with overlapping coverage; greedy picks optimally."""
    j1 = Journey("J-1", "Smoke", after=1, covers={"nav"}, tags=set(), description="go")
    j2 = Journey("J-2", "Venues", after=4, covers={"venues"}, tags=set(), description="go")
    j3 = Journey("J-3", "Full flow", after=9, covers={"nav", "venues", "events"}, tags=set(), description="go")
    j4 = Journey("J-4", "Events", after=9, covers={"events", "scheduling"}, tags=set(), description="go")
    selected = select_journeys([j1, j2, j3, j4])
    # J-3 covers 3 (nav, venues, events) → then J-4 adds scheduling → done
    assert len(selected) == 2
    assert selected[0].id == "J-3"
    assert selected[1].id == "J-4"


# ============================================
# End-to-end: select_journeys_for_milestone
# ============================================


def test_select_journeys_for_milestone_integration():
    """Full pipeline: parse JOURNEYS.md + BACKLOG.md → selected journeys."""
    selected = select_journeys_for_milestone(SAMPLE_JOURNEYS, SAMPLE_BACKLOG)
    # Stories 1, 2, 3, 6 are completed; J-1 (after:3) and J-2 (after:4→not done)
    # so only J-1 is eligible (after:3 ∈ {1,2,3,6})
    # J-2 (after:4) not eligible, J-7 (after:9) not eligible
    assert len(selected) == 1
    assert selected[0].id == "J-1"


def test_select_journeys_for_milestone_all_stories_done():
    """When all prerequisite stories are done, all journeys are eligible."""
    backlog = """\
1. [x] Scaffolding <!-- depends: none -->
2. [x] Auth <!-- depends: 1 -->
3. [x] Navigation <!-- depends: 1 -->
4. [x] Venues <!-- depends: 1 -->
5. [x] Members <!-- depends: 1, 2 -->
6. [x] Program Years <!-- depends: 1 -->
7. [x] Projects <!-- depends: 1, 6 -->
8. [x] Events <!-- depends: 4, 7 -->
9. [x] Event scheduling <!-- depends: 8 -->
"""
    selected = select_journeys_for_milestone(SAMPLE_JOURNEYS, backlog)
    # All three journeys eligible. J-7 covers 4 features including venues.crud,
    # so J-2 (only venues.crud) gets retired. J-1 covers nav (not in J-7).
    assert len(selected) == 2
    selected_ids = {j.id for j in selected}
    assert "J-7" in selected_ids
    assert "J-1" in selected_ids


def test_select_journeys_for_milestone_empty_journeys():
    assert select_journeys_for_milestone("", SAMPLE_BACKLOG) == []


def test_select_journeys_for_milestone_empty_backlog():
    assert select_journeys_for_milestone(SAMPLE_JOURNEYS, "") == []


def test_select_journeys_for_milestone_no_completed_stories():
    backlog = "1. [ ] Scaffolding <!-- depends: none -->\n"
    assert select_journeys_for_milestone(SAMPLE_JOURNEYS, backlog) == []


# ============================================
# Prompt formatting
# ============================================


def test_format_journey_prompt_block_empty():
    assert format_journey_prompt_block([]) == ""


def test_format_journey_prompt_block_single():
    j = Journey("J-1", "Smoke test", after=1, covers={"nav"}, tags=set(),
                description="Login → navigate sidebar → verify pages")
    block = format_journey_prompt_block([j])
    assert "J-1: Smoke test" in block
    assert "Login → navigate sidebar → verify pages" in block


def test_format_journey_prompt_block_multiple():
    j1 = Journey("J-1", "A", after=1, covers={"x"}, tags=set(), description="Step A")
    j2 = Journey("J-2", "B", after=2, covers={"y"}, tags=set(), description="Step B")
    block = format_journey_prompt_block([j1, j2])
    assert "J-1: A" in block
    assert "J-2: B" in block
    assert "Step A" in block
    assert "Step B" in block
