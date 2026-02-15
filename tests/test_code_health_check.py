"""Tests for code health check severity classification and range logic."""

import sys
import os

# Add scripts/ to path so we can import the health check module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from code_health_check import (
    classify_severity,
    split_by_severity,
    find_violations,
    count_all_violations,
    VIOLATION_CATEGORIES,
)


# ---------------------------------------------------------------------------
# classify_severity — pure function, no I/O
# ---------------------------------------------------------------------------

def test_below_warn_returns_none():
    assert classify_severity(30, warn_threshold=40, hard_threshold=60) is None


def test_at_warn_threshold_returns_none():
    """Exactly at the warn threshold is NOT a violation (must exceed)."""
    assert classify_severity(40, warn_threshold=40, hard_threshold=60) is None


def test_between_warn_and_hard_returns_advisory():
    assert classify_severity(50, warn_threshold=40, hard_threshold=60) == "advisory"


def test_at_hard_threshold_returns_advisory():
    """Exactly at the hard threshold is advisory (must exceed for violation)."""
    assert classify_severity(60, warn_threshold=40, hard_threshold=60) == "advisory"


def test_above_hard_returns_violation():
    assert classify_severity(61, warn_threshold=40, hard_threshold=60) == "violation"


def test_well_above_hard_returns_violation():
    assert classify_severity(200, warn_threshold=40, hard_threshold=60) == "violation"


def test_one_above_warn_returns_advisory():
    assert classify_severity(41, warn_threshold=40, hard_threshold=60) == "advisory"


# ---------------------------------------------------------------------------
# split_by_severity
# ---------------------------------------------------------------------------

def _make_violations(severities):
    """Helper: build a violations dict with oversized_functions of given severities."""
    result = {cat: [] for cat in VIOLATION_CATEGORIES}
    for sev in severities:
        result["oversized_functions"].append({
            "path": "test.py", "function": "f", "line": 1,
            "length": 50, "limit": 60, "severity": sev,
        })
    return result


def test_split_separates_advisory_from_hard():
    violations = _make_violations(["advisory", "violation", "advisory", "violation"])
    hard, advisory = split_by_severity(violations)
    assert len(hard["oversized_functions"]) == 2
    assert len(advisory["oversized_functions"]) == 2


def test_split_all_hard():
    violations = _make_violations(["violation", "violation"])
    hard, advisory = split_by_severity(violations)
    assert len(hard["oversized_functions"]) == 2
    assert len(advisory["oversized_functions"]) == 0


def test_split_all_advisory():
    violations = _make_violations(["advisory", "advisory"])
    hard, advisory = split_by_severity(violations)
    assert len(hard["oversized_functions"]) == 0
    assert len(advisory["oversized_functions"]) == 2


def test_split_empty():
    violations = {cat: [] for cat in VIOLATION_CATEGORIES}
    hard, advisory = split_by_severity(violations)
    assert count_all_violations(hard) == 0
    assert count_all_violations(advisory) == 0


def test_split_binary_rules_are_hard():
    """Binary rules (dead code, annotations, directories) should always be hard."""
    violations = {cat: [] for cat in VIOLATION_CATEGORIES}
    violations["dead_code"].append({
        "path": "test.py", "name": "unused_func", "line": 10, "severity": "violation",
    })
    violations["missing_annotations"].append({
        "path": "test.py", "function": "f", "line": 5,
        "missing_return": True, "missing_params": [], "missing_count": 1,
        "severity": "violation",
    })
    hard, advisory = split_by_severity(violations)
    assert len(hard["dead_code"]) == 1
    assert len(hard["missing_annotations"]) == 1
    assert count_all_violations(advisory) == 0


# ---------------------------------------------------------------------------
# find_violations — integration with severity
# ---------------------------------------------------------------------------

def _make_analysis(func_length=30, file_lines=200, nesting=2, complexity=5, params=3):
    """Helper: build a single-function analysis dict."""
    return {
        "path": "test.py",
        "file_lines": file_lines,
        "parse_error": False,
        "functions": [{
            "name": "my_func",
            "line": 1,
            "end_line": func_length,
            "length": func_length,
            "nesting_depth": nesting,
            "complexity": complexity,
            "param_count": params,
            "missing_return_annotation": False,
            "missing_param_annotations": [],
        }],
        "dead_code": [],
    }


_TEST_LIMITS = {
    "warn_func": 40, "hard_func": 60,
    "warn_file": 300, "hard_file": 500,
    "warn_depth": 4, "hard_depth": 6,
    "warn_complexity": 10, "hard_complexity": 15,
    "warn_params": 7, "hard_params": 10,
    "max_dir_depth": 5,
}


def test_function_in_advisory_range():
    analysis = _make_analysis(func_length=50)
    violations = find_violations([analysis], _TEST_LIMITS, "/nonexistent")
    assert len(violations["oversized_functions"]) == 1
    assert violations["oversized_functions"][0]["severity"] == "advisory"


def test_function_above_hard_limit():
    analysis = _make_analysis(func_length=70)
    violations = find_violations([analysis], _TEST_LIMITS, "/nonexistent")
    assert len(violations["oversized_functions"]) == 1
    assert violations["oversized_functions"][0]["severity"] == "violation"


def test_function_below_warn_not_flagged():
    analysis = _make_analysis(func_length=35)
    violations = find_violations([analysis], _TEST_LIMITS, "/nonexistent")
    assert len(violations["oversized_functions"]) == 0


def test_file_in_advisory_range():
    analysis = _make_analysis(file_lines=400)
    violations = find_violations([analysis], _TEST_LIMITS, "/nonexistent")
    assert len(violations["oversized_files"]) == 1
    assert violations["oversized_files"][0]["severity"] == "advisory"


def test_file_above_hard_limit():
    analysis = _make_analysis(file_lines=600)
    violations = find_violations([analysis], _TEST_LIMITS, "/nonexistent")
    assert len(violations["oversized_files"]) == 1
    assert violations["oversized_files"][0]["severity"] == "violation"


def test_complexity_in_advisory_range():
    analysis = _make_analysis(complexity=12)
    violations = find_violations([analysis], _TEST_LIMITS, "/nonexistent")
    assert len(violations["high_complexity"]) == 1
    assert violations["high_complexity"][0]["severity"] == "advisory"


def test_complexity_above_hard_limit():
    analysis = _make_analysis(complexity=20)
    violations = find_violations([analysis], _TEST_LIMITS, "/nonexistent")
    assert len(violations["high_complexity"]) == 1
    assert violations["high_complexity"][0]["severity"] == "violation"


def test_nesting_in_advisory_range():
    analysis = _make_analysis(nesting=5)
    violations = find_violations([analysis], _TEST_LIMITS, "/nonexistent")
    assert len(violations["deep_nesting"]) == 1
    assert violations["deep_nesting"][0]["severity"] == "advisory"


def test_params_in_advisory_range():
    analysis = _make_analysis(params=9)
    violations = find_violations([analysis], _TEST_LIMITS, "/nonexistent")
    assert len(violations["too_many_params"]) == 1
    assert violations["too_many_params"][0]["severity"] == "advisory"


def test_params_above_hard_limit():
    analysis = _make_analysis(params=12)
    violations = find_violations([analysis], _TEST_LIMITS, "/nonexistent")
    assert len(violations["too_many_params"]) == 1
    assert violations["too_many_params"][0]["severity"] == "violation"


def test_multiple_rules_fire_with_mixed_severity():
    """A function can trigger multiple rules at different severity levels."""
    analysis = _make_analysis(func_length=50, complexity=20, nesting=5)
    violations = find_violations([analysis], _TEST_LIMITS, "/nonexistent")
    assert violations["oversized_functions"][0]["severity"] == "advisory"
    assert violations["high_complexity"][0]["severity"] == "violation"
    assert violations["deep_nesting"][0]["severity"] == "advisory"


def test_clean_code_has_no_violations():
    analysis = _make_analysis(func_length=20, file_lines=100, nesting=2, complexity=3, params=2)
    violations = find_violations([analysis], _TEST_LIMITS, "/nonexistent")
    assert count_all_violations(violations) == 0
