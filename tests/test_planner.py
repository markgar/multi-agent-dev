"""Tests for planner helpers."""

from agentic_dev.planner import _FIRST_STORY_RE


BACKLOG_UNCHECKED = """\
# Backlog

1. [ ] Scaffolding — Create project structure <!-- depends: none -->
2. [ ] Members API — CRUD for members <!-- depends: 1 -->
3. [ ] Auth — Login endpoint <!-- depends: 2 -->
"""

BACKLOG_CHECKED = """\
# Backlog

1. [x] Scaffolding — Create project structure <!-- depends: none -->
2. [ ] Members API — CRUD for members <!-- depends: 1 -->
3. [ ] Auth — Login endpoint <!-- depends: 2 -->
"""

BACKLOG_IN_PROGRESS = """\
# Backlog

1. [~] Scaffolding — Create project structure <!-- depends: none -->
2. [ ] Members API — CRUD for members <!-- depends: 1 -->
"""


def test_first_story_regex_matches_unchecked():
    assert _FIRST_STORY_RE.search(BACKLOG_UNCHECKED) is not None


def test_first_story_regex_does_not_match_checked():
    assert _FIRST_STORY_RE.search(BACKLOG_CHECKED) is None


def test_first_story_regex_does_not_match_in_progress():
    assert _FIRST_STORY_RE.search(BACKLOG_IN_PROGRESS) is None


def test_first_story_substitution_checks_off_story_1():
    result = _FIRST_STORY_RE.sub(r"\1[x]\2", BACKLOG_UNCHECKED, count=1)
    assert "1. [x] Scaffolding" in result
    # Other stories remain unchecked
    assert "2. [ ] Members" in result
    assert "3. [ ] Auth" in result


def test_first_story_substitution_only_affects_story_1():
    """Ensure the regex doesn't match story 10, 11, etc."""
    content = "10. [ ] Some other story <!-- depends: 1 -->\n1. [ ] Scaffolding <!-- depends: none -->\n"
    matches = _FIRST_STORY_RE.findall(content)
    # Should only match the line starting with "1."
    assert len(matches) == 1
