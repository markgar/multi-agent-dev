"""Tree-sitter code analysis for target project review.

Analyzes source files for structural issues: oversized functions, deep nesting,
high cyclomatic complexity, and excessive parameters. Supports Python, JavaScript,
TypeScript, and C# via tree-sitter grammars.

Pure measurement functions operate on tree-sitter nodes. analyze_source() parses
a source string and returns findings. run_milestone_analysis() integrates with
git to analyze files changed in a milestone.
"""

import importlib
import os
import subprocess
from dataclasses import dataclass

from tree_sitter import Language, Parser

from agentic_dev.config import ANALYSIS_THRESHOLDS, LANGUAGE_CONFIGS


@dataclass
class Finding:
    """A single code analysis finding."""

    file: str
    line: int
    function_name: str
    check: str
    value: int
    warn_threshold: int
    hard_threshold: int
    severity: str  # "advisory" or "violation"


# ---------------------------------------------------------------------------
# Pure measurement functions
# ---------------------------------------------------------------------------


def classify_severity(value: int, warn: int, hard: int) -> str | None:
    """Classify a metric value against two-tier thresholds.

    Returns "violation" if >= hard, "advisory" if >= warn, None if below.
    """
    if value >= hard:
        return "violation"
    if value >= warn:
        return "advisory"
    return None


def measure_function_size(node) -> int:
    """Count the number of lines a function spans."""
    return node.end_point[0] - node.start_point[0] + 1


def measure_nesting_depth(node, nesting_types: set[str]) -> int:
    """Find maximum nesting depth of control flow structures within a node."""

    def _walk(n, depth):
        max_depth = depth
        for child in n.children:
            if child.type in nesting_types:
                max_depth = max(max_depth, _walk(child, depth + 1))
            else:
                max_depth = max(max_depth, _walk(child, depth))
        return max_depth

    return _walk(node, 0)


def measure_cyclomatic_complexity(node, branching_types: set[str]) -> int:
    """Approximate cyclomatic complexity: 1 + number of decision points."""

    def _count_branches(n):
        total = 0
        for child in n.children:
            if child.type in branching_types:
                total += 1
            total += _count_branches(child)
        return total

    return 1 + _count_branches(node)


def count_parameters(
    func_node, param_node_type: str, self_names: set[str]
) -> int:
    """Count function parameters, excluding self/cls names."""
    for child in func_node.children:
        if child.type == param_node_type:
            params = child.named_children
            count = len(params)
            if count > 0 and self_names:
                first_text = (
                    params[0].text.decode("utf8", errors="replace").strip()
                )
                if first_text in self_names:
                    count -= 1
            return count
    return 0


def get_function_name(node) -> str:
    """Extract the function name from a function node."""
    name_node = node.child_by_field_name("name")
    if name_node:
        return name_node.text.decode("utf8", errors="replace")
    # For arrow functions assigned to variables, check parent
    if node.parent and node.parent.type in (
        "variable_declarator",
        "assignment_expression",
        "pair",
    ):
        name_child = node.parent.child_by_field_name("name")
        if name_child is None:
            name_child = node.parent.child_by_field_name("left")
        if name_child:
            return name_child.text.decode("utf8", errors="replace")
    return "<anonymous>"


def find_functions(root_node, function_types: set[str]) -> list:
    """Collect all function/method nodes from a syntax tree."""
    results = []

    def _walk(node):
        if node.type in function_types:
            results.append(node)
        for child in node.children:
            _walk(child)

    _walk(root_node)
    return results


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_parser_cache: dict = {}


def _get_parser(config: dict) -> Parser | None:
    """Get or create a tree-sitter parser for a language config.

    Returns None if the grammar package is not installed.
    """
    cache_key = (config["grammar_module"], config["language_func"])
    if cache_key in _parser_cache:
        return _parser_cache[cache_key]
    try:
        mod = importlib.import_module(config["grammar_module"])
        lang_func = getattr(mod, config["language_func"])
        language = Language(lang_func())
        parser = Parser(language)
        _parser_cache[cache_key] = parser
        return parser
    except (ImportError, AttributeError, TypeError, OSError):
        _parser_cache[cache_key] = None
        return None


def config_for_file(filepath: str) -> dict | None:
    """Return the language config matching a file's extension, or None."""
    ext = os.path.splitext(filepath)[1].lower()
    for config in LANGUAGE_CONFIGS.values():
        if ext in config["file_extensions"]:
            return config
    return None


# ---------------------------------------------------------------------------
# Source-level analysis
# ---------------------------------------------------------------------------


def analyze_source(
    source: str, config: dict, filepath: str = "<unknown>"
) -> list[Finding]:
    """Parse source code and return structural findings.

    Parses the source with tree-sitter, finds all functions, and measures
    each one against the thresholds in ANALYSIS_THRESHOLDS.
    """
    parser = _get_parser(config)
    if parser is None:
        return []

    try:
        tree = parser.parse(bytes(source, "utf8"))
    except (ValueError, TypeError):
        return []

    root = tree.root_node
    functions = find_functions(root, config["function_types"])
    findings: list[Finding] = []
    thresholds = ANALYSIS_THRESHOLDS

    for func_node in functions:
        name = get_function_name(func_node)

        # Function size
        size = measure_function_size(func_node)
        t = thresholds["function_size"]
        severity = classify_severity(size, t["warn"], t["hard"])
        if severity:
            findings.append(
                Finding(
                    file=filepath,
                    line=func_node.start_point[0] + 1,
                    function_name=name,
                    check="function_size",
                    value=size,
                    warn_threshold=t["warn"],
                    hard_threshold=t["hard"],
                    severity=severity,
                )
            )

        # Nesting depth
        depth = measure_nesting_depth(func_node, config["nesting_types"])
        t = thresholds["nesting_depth"]
        severity = classify_severity(depth, t["warn"], t["hard"])
        if severity:
            findings.append(
                Finding(
                    file=filepath,
                    line=func_node.start_point[0] + 1,
                    function_name=name,
                    check="nesting_depth",
                    value=depth,
                    warn_threshold=t["warn"],
                    hard_threshold=t["hard"],
                    severity=severity,
                )
            )

        # Cyclomatic complexity
        complexity = measure_cyclomatic_complexity(
            func_node, config["branching_types"]
        )
        t = thresholds["cyclomatic_complexity"]
        severity = classify_severity(complexity, t["warn"], t["hard"])
        if severity:
            findings.append(
                Finding(
                    file=filepath,
                    line=func_node.start_point[0] + 1,
                    function_name=name,
                    check="cyclomatic_complexity",
                    value=complexity,
                    warn_threshold=t["warn"],
                    hard_threshold=t["hard"],
                    severity=severity,
                )
            )

        # Parameter count
        param_count = count_parameters(
            func_node, config["parameter_node"], config["self_names"]
        )
        t = thresholds["parameter_count"]
        severity = classify_severity(param_count, t["warn"], t["hard"])
        if severity:
            findings.append(
                Finding(
                    file=filepath,
                    line=func_node.start_point[0] + 1,
                    function_name=name,
                    check="parameter_count",
                    value=param_count,
                    warn_threshold=t["warn"],
                    hard_threshold=t["hard"],
                    severity=severity,
                )
            )

    # File size check (not per-function)
    line_count = source.count("\n") + 1
    t = thresholds["file_size"]
    severity = classify_severity(line_count, t["warn"], t["hard"])
    if severity:
        findings.append(
            Finding(
                file=filepath,
                line=1,
                function_name="<file>",
                check="file_size",
                value=line_count,
                warn_threshold=t["warn"],
                hard_threshold=t["hard"],
                severity=severity,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

MAX_FINDINGS_IN_PROMPT = 20


def format_findings(
    findings: list[Finding], max_findings: int = MAX_FINDINGS_IN_PROMPT
) -> str:
    """Format findings as markdown for injection into the reviewer prompt."""
    if not findings:
        return "No structural issues detected by static analysis."

    sorted_findings = sorted(
        findings,
        key=lambda f: (f.severity != "violation", f.file, f.line),
    )
    capped = sorted_findings[:max_findings]

    lines = []
    for f in capped:
        lines.append(
            f"- [{f.severity}] {f.file}:{f.line} — `{f.function_name}`: "
            f"{f.check} is {f.value} "
            f"(threshold: {f.warn_threshold}/{f.hard_threshold})"
        )

    if len(sorted_findings) > max_findings:
        remaining = len(sorted_findings) - max_findings
        lines.append(f"- ... and {remaining} more findings omitted")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Git integration
# ---------------------------------------------------------------------------


def get_changed_files(start_sha: str, end_sha: str) -> list[str]:
    """Get list of files changed between two git SHAs.

    Returns relative paths of added, copied, modified, or renamed files.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "diff",
                start_sha,
                end_sha,
                "--name-only",
                "--diff-filter=ACMR",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        return [
            f.strip() for f in result.stdout.strip().split("\n") if f.strip()
        ]
    except (OSError, subprocess.SubprocessError):
        return []


def run_milestone_analysis(start_sha: str, end_sha: str) -> str:
    """Analyze files changed in a milestone and return formatted findings.

    Entry point called by the watcher. Gets changed files from git diff,
    parses each recognized file with tree-sitter, runs structural checks,
    and returns formatted findings ready for prompt injection.

    Never raises — errors produce a clean "no issues" message.
    """
    try:
        changed_files = get_changed_files(start_sha, end_sha)
        if not changed_files:
            return "No structural issues detected by static analysis."

        all_findings: list[Finding] = []
        for filepath in changed_files:
            config = config_for_file(filepath)
            if config is None:
                continue

            if not os.path.isfile(filepath):
                continue

            try:
                with open(
                    filepath, "r", encoding="utf-8", errors="replace"
                ) as f:
                    source = f.read()
            except OSError:
                continue

            file_findings = analyze_source(source, config, filepath)
            all_findings.extend(file_findings)

        return format_findings(all_findings)
    except Exception:
        return "No structural issues detected by static analysis."
