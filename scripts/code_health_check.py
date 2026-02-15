"""Code health checker for agent-maintained codebases.

Analyzes Python source files for:
- Functions exceeding a maximum line count
- Files exceeding a maximum line count
- Excessive nesting depth in functions
- High cyclomatic complexity in functions
- Functions with too many parameters
- Functions missing type annotations
- Unused module-level definitions (dead code)
- Excessive directory nesting depth

Supports a baseline file to suppress known violations. Suppressed violations
reappear if the code gets worse. Run with --update-baseline to record current
violations.

Outputs a structured report suitable for GitHub Issues.

Usage:
    python scripts/code_health_check.py [--src-dir src/agent] [--max-func 40] [--max-file 300] [--max-depth 4]
    python scripts/code_health_check.py --format json
    python scripts/code_health_check.py --update-baseline
    python scripts/code_health_check.py --baseline .code-health-baseline.json
"""
import argparse
import ast
import json
import os
import sys

DEFAULT_SRC_DIR = "src/agent"
DEFAULT_WARN_FUNC_LINES = 40
DEFAULT_HARD_FUNC_LINES = 60
DEFAULT_WARN_FILE_LINES = 300
DEFAULT_HARD_FILE_LINES = 500
DEFAULT_WARN_NESTING_DEPTH = 4
DEFAULT_HARD_NESTING_DEPTH = 6
DEFAULT_WARN_COMPLEXITY = 10
DEFAULT_HARD_COMPLEXITY = 15
DEFAULT_WARN_PARAMS = 7
DEFAULT_HARD_PARAMS = 10
DEFAULT_MAX_DIR_DEPTH = 5
DEFAULT_BASELINE_FILE = ".code-health-baseline.json"

# All violation category keys, in report order
VIOLATION_CATEGORIES = [
    "oversized_functions",
    "oversized_files",
    "deep_nesting",
    "high_complexity",
    "too_many_params",
    "missing_annotations",
    "dead_code",
    "deep_directories",
]


# ---------------------------------------------------------------------------
# AST measurement helpers (pure functions)
# ---------------------------------------------------------------------------

def measure_nesting_depth(node, current_depth=0):
    """Return the maximum nesting depth of control-flow statements inside a node."""
    max_depth = current_depth
    nesting_nodes = (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.ExceptHandler)
    for child in ast.iter_child_nodes(node):
        if isinstance(child, nesting_nodes):
            max_depth = max(max_depth, measure_nesting_depth(child, current_depth + 1))
        else:
            max_depth = max(max_depth, measure_nesting_depth(child, current_depth))
    return max_depth


def measure_cyclomatic_complexity(node):
    """Count the cyclomatic complexity of a function AST node.

    Starts at 1 (the function itself) and adds 1 for each branching construct:
    if, elif, for, while, except, assert, and, or, ternary (IfExp).
    """
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.IfExp)):
            complexity += 1
        elif isinstance(child, (ast.For, ast.While, ast.AsyncFor)):
            complexity += 1
        elif isinstance(child, ast.ExceptHandler):
            complexity += 1
        elif isinstance(child, ast.Assert):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            # 'a and b and c' has 2 ops → adds 2
            complexity += len(child.values) - 1
    return complexity


def count_parameters(node):
    """Count the number of parameters in a function definition, excluding self/cls."""
    args = node.args
    all_args = args.posonlyargs + args.args + args.kwonlyargs
    count = len(all_args)
    if args.vararg:
        count += 1
    if args.kwarg:
        count += 1
    # Exclude self/cls for methods
    if all_args and all_args[0].arg in ("self", "cls"):
        count -= 1
    return count


def check_type_annotations(node):
    """Check whether a function has return annotation and parameter annotations.

    Returns (missing_return, missing_param_names) where missing_return is bool
    and missing_param_names is a list of parameter names without annotations.
    """
    missing_return = node.returns is None
    missing_params = []
    all_args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
    for arg in all_args:
        if arg.arg in ("self", "cls"):
            continue
        if arg.annotation is None:
            missing_params.append(arg.arg)
    return missing_return, missing_params


def find_defined_names(tree):
    """Return a dict of top-level names defined in a module: {name: line}.

    Includes functions, classes, and variable assignments at module scope.
    Skips __dunder__ names, _CONSTANTS used as module config, and __all__.
    """
    defined = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined[node.name] = node.lineno
        elif isinstance(node, ast.ClassDef):
            defined[node.name] = node.lineno
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = []
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets = [node.target]
            elif isinstance(node, ast.Assign):
                targets = [t for t in node.targets if isinstance(t, ast.Name)]
            for t in targets:
                defined[t.id] = node.lineno
    return defined


def find_used_names(tree):
    """Return the set of all names referenced in a module (excluding definitions themselves)."""
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            # Capture the root of chained attribute access (e.g. 'os' in os.path)
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                used.add(root.id)
    return used


def find_dead_code(tree, path):
    """Find module-level definitions that appear unused within the file.

    Returns a list of {"name": str, "line": int} for each unused definition.
    Skips dunder names, single-underscore private names used as constants,
    and names exported via __all__.

    Note: This is intra-file only. Use filter_dead_code_with_cross_imports()
    after collecting all analyses to remove false positives from cross-file imports.
    """
    defined = find_defined_names(tree)
    used = find_used_names(tree)

    # Check for __all__ — if present, anything listed there counts as used
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                used.add(elt.value)

    # Also treat decorator references as usage — both the decorator name
    # and the decorated function (framework-registered via @app.command() etc.)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name):
                    used.add(dec.id)
                elif isinstance(dec, ast.Attribute):
                    root = dec
                    while isinstance(root, ast.Attribute):
                        root = root.value
                    if isinstance(root, ast.Name):
                        used.add(root.id)
                elif isinstance(dec, ast.Call):
                    # @app.command(), @app.callback() etc. — the decorated function is used
                    used.add(node.name)

    unused = []
    for name, line in sorted(defined.items(), key=lambda x: x[1]):
        # Skip dunder names and __all__
        if name.startswith("__") and name.endswith("__"):
            continue
        # Skip names starting with _ (often module-level constants or private helpers
        # that are used via import in other modules)
        if name.startswith("_"):
            continue
        if name not in used:
            unused.append({"name": name, "line": line})
    return unused


def collect_cross_file_imports(file_paths):
    """Scan all files and return the set of names imported/referenced from other modules.

    This captures:
    - 'from module import name' style imports
    - 'module.name' attribute access (covers module.register() patterns)
    - decorator-registered functions (typer app.command() etc.)

    Used to filter dead code false positives — if a name is imported
    by another file, it's not dead.
    """
    imported_names = set()
    for path in file_paths:
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported_names.add(alias.name)
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                imported_names.add(node.attr)
    return imported_names


def filter_dead_code_with_cross_imports(analyses, all_file_paths):
    """Remove dead code entries that are imported by other files in the project."""
    imported = collect_cross_file_imports(all_file_paths)
    for analysis in analyses:
        analysis["dead_code"] = [
            d for d in analysis.get("dead_code", [])
            if d["name"] not in imported
        ]


# ---------------------------------------------------------------------------
# File and directory analysis
# ---------------------------------------------------------------------------

def analyze_file(path):
    """Analyze a single Python file. Returns dict with file_lines, functions, dead_code."""
    with open(path, encoding="utf-8") as f:
        source = f.read()

    file_lines = len(source.splitlines())

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {
            "path": path, "file_lines": file_lines,
            "functions": [], "dead_code": [], "parse_error": True,
        }

    functions = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end_line = getattr(node, "end_lineno", node.lineno)
        length = end_line - node.lineno + 1
        depth = measure_nesting_depth(node)
        complexity = measure_cyclomatic_complexity(node)
        param_count = count_parameters(node)
        missing_return, missing_params = check_type_annotations(node)
        functions.append({
            "name": node.name,
            "line": node.lineno,
            "end_line": end_line,
            "length": length,
            "nesting_depth": depth,
            "complexity": complexity,
            "param_count": param_count,
            "missing_return_annotation": missing_return,
            "missing_param_annotations": missing_params,
        })

    dead = find_dead_code(tree, path)
    return {
        "path": path, "file_lines": file_lines,
        "functions": functions, "dead_code": dead, "parse_error": False,
    }


def collect_files(src_dir):
    """Walk src_dir and return a list of .py file paths (excluding __pycache__)."""
    paths = []
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                paths.append(os.path.join(root, f))
    paths.sort()
    return paths


def measure_directory_depth(src_dir):
    """Return a list of (dirpath, depth) for all directories under src_dir.

    depth is relative to src_dir (src_dir itself is depth 0).
    """
    src_dir = os.path.normpath(src_dir)
    base_depth = src_dir.count(os.sep)
    results = []
    for root, dirs, _files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        depth = os.path.normpath(root).count(os.sep) - base_depth
        results.append((root, depth))
    return results


# ---------------------------------------------------------------------------
# Severity classification
# ---------------------------------------------------------------------------

def classify_severity(value, warn_threshold, hard_threshold):
    """Classify a measured value into a severity level.

    Returns 'violation' if value exceeds the hard threshold,
    'advisory' if it exceeds the warn threshold but not the hard,
    or None if it's within acceptable range.
    """
    if value > hard_threshold:
        return "violation"
    if value > warn_threshold:
        return "advisory"
    return None


def split_by_severity(violations):
    """Split a violations dict into (hard, advisory) dicts by severity field.

    Hard violations have severity='violation' or no severity field (binary rules).
    Advisory violations have severity='advisory'.
    Returns (hard_dict, advisory_dict) with the same category keys.
    """
    hard = {cat: [] for cat in VIOLATION_CATEGORIES}
    advisory = {cat: [] for cat in VIOLATION_CATEGORIES}
    for cat in VIOLATION_CATEGORIES:
        for v in violations.get(cat, []):
            if v.get("severity") == "advisory":
                advisory[cat].append(v)
            else:
                hard[cat].append(v)
    return hard, advisory


# ---------------------------------------------------------------------------
# Violation detection
# ---------------------------------------------------------------------------

def find_violations(analyses, limits, src_dir):
    """Find all violations across analyses. Returns a dict keyed by category.

    Each violation includes a 'severity' field: 'advisory' for values between
    warn and hard thresholds (LLM reviewer decides), 'violation' for values
    exceeding the hard threshold (always filed). Binary rules (dead code,
    missing annotations, directory depth) are always 'violation'.
    """
    violations = {cat: [] for cat in VIOLATION_CATEGORIES}

    for analysis in analyses:
        path = analysis["path"]

        file_severity = classify_severity(
            analysis["file_lines"], limits["warn_file"], limits["hard_file"]
        )
        if file_severity:
            violations["oversized_files"].append({
                "path": path,
                "lines": analysis["file_lines"],
                "limit": limits["hard_file"],
                "warn_limit": limits["warn_file"],
                "severity": file_severity,
            })

        for func in analysis["functions"]:
            func_severity = classify_severity(
                func["length"], limits["warn_func"], limits["hard_func"]
            )
            if func_severity:
                violations["oversized_functions"].append({
                    "path": path,
                    "function": func["name"],
                    "line": func["line"],
                    "length": func["length"],
                    "limit": limits["hard_func"],
                    "warn_limit": limits["warn_func"],
                    "severity": func_severity,
                })

            depth_severity = classify_severity(
                func["nesting_depth"], limits["warn_depth"], limits["hard_depth"]
            )
            if depth_severity:
                violations["deep_nesting"].append({
                    "path": path,
                    "function": func["name"],
                    "line": func["line"],
                    "depth": func["nesting_depth"],
                    "limit": limits["hard_depth"],
                    "warn_limit": limits["warn_depth"],
                    "severity": depth_severity,
                })

            complexity_severity = classify_severity(
                func["complexity"], limits["warn_complexity"], limits["hard_complexity"]
            )
            if complexity_severity:
                violations["high_complexity"].append({
                    "path": path,
                    "function": func["name"],
                    "line": func["line"],
                    "complexity": func["complexity"],
                    "limit": limits["hard_complexity"],
                    "warn_limit": limits["warn_complexity"],
                    "severity": complexity_severity,
                })

            params_severity = classify_severity(
                func["param_count"], limits["warn_params"], limits["hard_params"]
            )
            if params_severity:
                violations["too_many_params"].append({
                    "path": path,
                    "function": func["name"],
                    "line": func["line"],
                    "param_count": func["param_count"],
                    "limit": limits["hard_params"],
                    "warn_limit": limits["warn_params"],
                    "severity": params_severity,
                })

            # Binary rule — no range, always 'violation'
            missing_count = len(func["missing_param_annotations"])
            if func["missing_return_annotation"]:
                missing_count += 1
            if missing_count > 0 and not func["name"].startswith("_"):
                violations["missing_annotations"].append({
                    "path": path,
                    "function": func["name"],
                    "line": func["line"],
                    "missing_return": func["missing_return_annotation"],
                    "missing_params": func["missing_param_annotations"],
                    "missing_count": missing_count,
                    "severity": "violation",
                })

        # Binary rule — no range, always 'violation'
        for dead in analysis.get("dead_code", []):
            violations["dead_code"].append({
                "path": path,
                "name": dead["name"],
                "line": dead["line"],
                "severity": "violation",
            })

    # Binary rule — no range, always 'violation'
    for dirpath, depth in measure_directory_depth(src_dir):
        if depth > limits["max_dir_depth"]:
            violations["deep_directories"].append({
                "path": dirpath,
                "depth": depth,
                "limit": limits["max_dir_depth"],
                "severity": "violation",
            })

    # Sort for consistent output
    violations["oversized_functions"].sort(key=lambda x: -x["length"])
    violations["oversized_files"].sort(key=lambda x: -x["lines"])
    violations["deep_nesting"].sort(key=lambda x: -x["depth"])
    violations["high_complexity"].sort(key=lambda x: -x["complexity"])
    violations["too_many_params"].sort(key=lambda x: -x["param_count"])
    violations["missing_annotations"].sort(key=lambda x: -x["missing_count"])
    violations["deep_directories"].sort(key=lambda x: -x["depth"])
    return violations


# ---------------------------------------------------------------------------
# Baseline support
# ---------------------------------------------------------------------------

def _make_key(v, *fields):
    """Build a baseline lookup key from violation fields."""
    return "::".join(str(v.get(f, "")) for f in fields)


def load_baseline(path):
    """Load a baseline file. Returns dict keyed by category, each a dict of key→entry."""
    if not path or not os.path.exists(path):
        return {cat: {} for cat in VIOLATION_CATEGORIES}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    baseline = {}
    for cat in VIOLATION_CATEGORIES:
        entries = data.get(cat, [])
        baseline[cat] = {e["key"]: e for e in entries if "key" in e}
    return baseline


def save_baseline(path, violations):
    """Write current violations to a baseline file for future suppression."""
    data = {}
    for cat in VIOLATION_CATEGORIES:
        items = []
        for v in violations.get(cat, []):
            entry = dict(v)
            entry["key"] = _baseline_key_for(cat, v)
            items.append(entry)
        data[cat] = items
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _baseline_key_for(cat, v):
    """Generate the unique baseline key for a violation."""
    if cat in ("oversized_files", "deep_directories"):
        return v["path"]
    if cat == "dead_code":
        return "{}::{}".format(v["path"], v["name"])
    return "{}::{}".format(v["path"], v["function"])


# Map of category → (field_to_compare, "higher is worse")
_BASELINE_COMPARE_FIELD = {
    "oversized_functions": "length",
    "oversized_files": "lines",
    "deep_nesting": "depth",
    "high_complexity": "complexity",
    "too_many_params": "param_count",
    "missing_annotations": "missing_count",
    "dead_code": None,  # presence-only — if in baseline, suppress
    "deep_directories": "depth",
}


def filter_violations_against_baseline(violations, baseline):
    """Remove violations in the baseline that haven't gotten worse."""
    filtered = {}
    for cat in VIOLATION_CATEGORIES:
        compare_field = _BASELINE_COMPARE_FIELD.get(cat)
        result = []
        for v in violations.get(cat, []):
            key = _baseline_key_for(cat, v)
            entry = baseline.get(cat, {}).get(key)
            if not entry:
                result.append(v)
                continue
            if compare_field is None:
                continue  # presence-only suppression
            if v.get(compare_field, 0) > entry.get(compare_field, 0):
                result.append(v)  # got worse — resurface
            # else: suppressed
        filtered[cat] = result
    return filtered


def count_all_violations(violations):
    """Sum violations across all categories."""
    return sum(len(violations.get(cat, [])) for cat in VIOLATION_CATEGORIES)


def count_baselined(violations, filtered):
    """Count how many violations were suppressed by the baseline."""
    return count_all_violations(violations) - count_all_violations(filtered)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _severity_label(severity):
    """Return a display label for a severity level."""
    if severity == "advisory":
        return "advisory"
    return "VIOLATION"


def format_markdown_report(violations, limits, baselined_count=0):
    """Format violations as a GitHub Issue-friendly markdown report.

    Separates hard violations (must fix) from advisory items (LLM reviewer
    decides). Each table row shows a Severity column.
    """
    total = count_all_violations(violations)
    hard, advisory = split_by_severity(violations)
    hard_count = count_all_violations(hard)
    advisory_count = count_all_violations(advisory)

    if total == 0:
        return "## Code Health Check: All Clear\n\nNo violations found. All files and functions are within limits."

    lines = []
    lines.append("## Code Health Check: {} issue{} found\n".format(total, "s" if total != 1 else ""))
    lines.append("This is an automated report from the code health checker.")
    lines.append("The codebase guidelines recommend small, single-purpose functions ")
    lines.append("with flat control flow for agent-maintained code.\n")
    if hard_count:
        lines.append("**{} hard violation{}** (must fix) and **{} advisory** (reviewer judgment).\n".format(
            hard_count, "s" if hard_count != 1 else "", advisory_count))
    elif advisory_count:
        lines.append("**{} advisory item{}** for reviewer judgment (no hard violations).\n".format(
            advisory_count, "s" if advisory_count != 1 else ""))
    if baselined_count > 0:
        lines.append("_{} known violation{} suppressed by baseline. ".format(
            baselined_count, "s" if baselined_count != 1 else ""))
        lines.append("These will reappear if the code gets worse._\n")

    if violations.get("oversized_functions"):
        lines.append("### Oversized Functions (advisory: >{} lines, hard: >{} lines)\n".format(
            limits["warn_func"], limits["hard_func"]))
        lines.append("| Severity | Function | File | Line | Length | Over by |")
        lines.append("|----------|----------|------|------|--------|---------|")
        for v in violations["oversized_functions"]:
            threshold = v["limit"] if v["severity"] == "violation" else v.get("warn_limit", v["limit"])
            over = v["length"] - threshold
            lines.append("| {} | `{}` | {} | L{} | **{}** | +{} |".format(
                _severity_label(v["severity"]), v["function"], v["path"], v["line"], v["length"], over))
        lines.append("")

    if violations.get("oversized_files"):
        lines.append("### Oversized Files (advisory: >{} lines, hard: >{} lines)\n".format(
            limits["warn_file"], limits["hard_file"]))
        lines.append("| Severity | File | Lines | Over by |")
        lines.append("|----------|------|-------|---------|")
        for v in violations["oversized_files"]:
            threshold = v["limit"] if v["severity"] == "violation" else v.get("warn_limit", v["limit"])
            over = v["lines"] - threshold
            lines.append("| {} | {} | **{}** | +{} |".format(
                _severity_label(v["severity"]), v["path"], v["lines"], over))
        lines.append("")

    if violations.get("deep_nesting"):
        lines.append("### Excessive Nesting (advisory: >{} levels, hard: >{} levels)\n".format(
            limits["warn_depth"], limits["hard_depth"]))
        lines.append("| Severity | Function | File | Line | Depth |")
        lines.append("|----------|----------|------|------|-------|")
        for v in violations["deep_nesting"]:
            lines.append("| {} | `{}` | {} | L{} | **{}** |".format(
                _severity_label(v["severity"]), v["function"], v["path"], v["line"], v["depth"]))
        lines.append("")

    if violations.get("high_complexity"):
        lines.append("### High Cyclomatic Complexity (advisory: >{}, hard: >{})\n".format(
            limits["warn_complexity"], limits["hard_complexity"]))
        lines.append("| Severity | Function | File | Line | Complexity |")
        lines.append("|----------|----------|------|------|------------|")
        for v in violations["high_complexity"]:
            lines.append("| {} | `{}` | {} | L{} | **{}** |".format(
                _severity_label(v["severity"]), v["function"], v["path"], v["line"], v["complexity"]))
        lines.append("")

    if violations.get("too_many_params"):
        lines.append("### Too Many Parameters (advisory: >{}, hard: >{})\n".format(
            limits["warn_params"], limits["hard_params"]))
        lines.append("| Severity | Function | File | Line | Params |")
        lines.append("|----------|----------|------|------|--------|")
        for v in violations["too_many_params"]:
            lines.append("| {} | `{}` | {} | L{} | **{}** |".format(
                _severity_label(v["severity"]), v["function"], v["path"], v["line"], v["param_count"]))
        lines.append("")

    if violations.get("missing_annotations"):
        lines.append("### Missing Type Annotations\n")
        lines.append("| Function | File | Line | Missing |")
        lines.append("|----------|------|------|---------|")
        for v in violations["missing_annotations"]:
            parts = []
            if v["missing_return"]:
                parts.append("return")
            if v["missing_params"]:
                parts.extend(v["missing_params"])
            lines.append("| `{}` | {} | L{} | {} |".format(
                v["function"], v["path"], v["line"], ", ".join(parts)))
        lines.append("")

    if violations.get("dead_code"):
        lines.append("### Potentially Unused Definitions\n")
        lines.append("| Name | File | Line |")
        lines.append("|------|------|------|")
        for v in violations["dead_code"]:
            lines.append("| `{}` | {} | L{} |".format(v["name"], v["path"], v["line"]))
        lines.append("")
        lines.append("_Note: Dead code detection is intra-file only. These definitions may ")
        lines.append("be imported by other modules. Verify before removing._\n")

    if violations.get("deep_directories"):
        lines.append("### Deep Directory Nesting (limit: {} levels)\n".format(limits["max_dir_depth"]))
        lines.append("| Directory | Depth |")
        lines.append("|-----------|-------|")
        for v in violations["deep_directories"]:
            lines.append("| {} | **{}** |".format(v["path"], v["depth"]))
        lines.append("")

    lines.append("### Recommendations\n")
    lines.append("- Extract helper functions from oversized functions")
    lines.append("- Use early returns to flatten deep nesting")
    lines.append("- Split large files by extracting related helpers into new modules")
    lines.append("- Reduce complexity by extracting conditional branches into named helpers")
    lines.append("- Group related parameters into dataclasses or typed dicts")
    lines.append("- Add type annotations to public function signatures")
    lines.append("- Remove unused definitions to reduce context waste for agents")
    lines.append("- Flatten directory structure to keep related files easy to discover\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Code health checker for agent-maintained codebases")
    parser.add_argument("--src-dir", default=DEFAULT_SRC_DIR, help="Source directory to analyze")
    # Warn thresholds (advisory range — LLM reviewer decides)
    parser.add_argument("--warn-func", type=int, default=DEFAULT_WARN_FUNC_LINES,
                        help="Advisory threshold for function lines (warn..hard = advisory)")
    parser.add_argument("--warn-file", type=int, default=DEFAULT_WARN_FILE_LINES,
                        help="Advisory threshold for file lines")
    parser.add_argument("--warn-depth", type=int, default=DEFAULT_WARN_NESTING_DEPTH,
                        help="Advisory threshold for nesting depth")
    parser.add_argument("--warn-complexity", type=int, default=DEFAULT_WARN_COMPLEXITY,
                        help="Advisory threshold for cyclomatic complexity")
    parser.add_argument("--warn-params", type=int, default=DEFAULT_WARN_PARAMS,
                        help="Advisory threshold for parameter count")
    # Hard thresholds (always filed — no judgment needed)
    parser.add_argument("--hard-func", type=int, default=DEFAULT_HARD_FUNC_LINES,
                        help="Hard limit for function lines (always a violation)")
    parser.add_argument("--hard-file", type=int, default=DEFAULT_HARD_FILE_LINES,
                        help="Hard limit for file lines")
    parser.add_argument("--hard-depth", type=int, default=DEFAULT_HARD_NESTING_DEPTH,
                        help="Hard limit for nesting depth")
    parser.add_argument("--hard-complexity", type=int, default=DEFAULT_HARD_COMPLEXITY,
                        help="Hard limit for cyclomatic complexity")
    parser.add_argument("--hard-params", type=int, default=DEFAULT_HARD_PARAMS,
                        help="Hard limit for parameter count")
    # Binary rules (no range)
    parser.add_argument("--max-dir-depth", type=int, default=DEFAULT_MAX_DIR_DEPTH,
                        help="Max directory nesting depth relative to src-dir")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    parser.add_argument("--baseline", default=None,
                        help="Path to baseline JSON file. Suppresses known violations unless they get worse.")
    parser.add_argument("--update-baseline", action="store_true",
                        help="Write current violations to the baseline file and exit.")
    args = parser.parse_args()

    limits = {
        "warn_func": args.warn_func,
        "hard_func": args.hard_func,
        "warn_file": args.warn_file,
        "hard_file": args.hard_file,
        "warn_depth": args.warn_depth,
        "hard_depth": args.hard_depth,
        "warn_complexity": args.warn_complexity,
        "hard_complexity": args.hard_complexity,
        "warn_params": args.warn_params,
        "hard_params": args.hard_params,
        "max_dir_depth": args.max_dir_depth,
    }

    files = collect_files(args.src_dir)
    if not files:
        print("No Python files found in {}".format(args.src_dir), file=sys.stderr)
        sys.exit(1)

    analyses = [analyze_file(f) for f in files]
    filter_dead_code_with_cross_imports(analyses, files)
    violations = find_violations(analyses, limits, args.src_dir)

    if args.update_baseline:
        baseline_path = args.baseline or DEFAULT_BASELINE_FILE
        save_baseline(baseline_path, violations)
        total = count_all_violations(violations)
        print("Baseline written to {} ({} violations recorded)".format(baseline_path, total))
        sys.exit(0)

    baselined_count = 0
    if args.baseline:
        baseline = load_baseline(args.baseline)
        filtered = filter_violations_against_baseline(violations, baseline)
        baselined_count = count_baselined(violations, filtered)
        violations = filtered

    total = count_all_violations(violations)
    hard, advisory = split_by_severity(violations)
    hard_count = count_all_violations(hard)
    advisory_count = count_all_violations(advisory)

    if args.format == "json":
        output = {
            "violations": violations,
            "hard_violations": hard,
            "advisory_violations": advisory,
            "summary": {
                "total_violations": total,
                "hard_violations": hard_count,
                "advisory_violations": advisory_count,
                "baselined_violations": baselined_count,
                "files_analyzed": len(files),
                "limits": limits,
            },
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_markdown_report(violations, limits, baselined_count))

    # Exit code 1 only for hard violations — advisory items don't fail the check
    sys.exit(1 if hard_count > 0 else 0)


if __name__ == "__main__":
    main()
