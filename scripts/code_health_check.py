"""Code health checker for agent-maintained codebases.

Analyzes Python source files for:
- Functions exceeding a maximum line count
- Files exceeding a maximum line count
- Excessive nesting depth in functions

Supports a baseline file to suppress known violations. Suppressed violations
reappear if the code gets worse (function grows longer, nesting gets deeper,
file grows larger). Run with --update-baseline to record current violations.

Outputs a structured report suitable for GitHub Issues.

Usage:
    python scripts/code_health_check.py [--src-dir src/agent] [--max-func 40] [--max-file 300] [--max-depth 4]
    python scripts/code_health_check.py --format json
    python scripts/code_health_check.py --update-baseline          # record current violations as accepted
    python scripts/code_health_check.py --baseline .code-health-baseline.json  # filter against baseline
"""
import argparse
import ast
import json
import os
import sys

DEFAULT_SRC_DIR = "src/agent"
DEFAULT_MAX_FUNC_LINES = 40
DEFAULT_MAX_FILE_LINES = 300
DEFAULT_MAX_NESTING_DEPTH = 4
DEFAULT_BASELINE_FILE = ".code-health-baseline.json"


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


def analyze_file(path):
    """Analyze a single Python file. Returns dict with file_lines, functions list."""
    with open(path, encoding="utf-8") as f:
        source = f.read()

    file_lines = len(source.splitlines())

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"path": path, "file_lines": file_lines, "functions": [], "parse_error": True}

    functions = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end_line = getattr(node, "end_lineno", node.lineno)
        length = end_line - node.lineno + 1
        depth = measure_nesting_depth(node)
        functions.append({
            "name": node.name,
            "line": node.lineno,
            "end_line": end_line,
            "length": length,
            "nesting_depth": depth,
        })

    return {"path": path, "file_lines": file_lines, "functions": functions, "parse_error": False}


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


def find_violations(analyses, max_func_lines, max_file_lines, max_nesting_depth):
    """Return a dict with oversized_files, oversized_functions, deep_nesting lists."""
    oversized_files = []
    oversized_functions = []
    deep_nesting = []

    for analysis in analyses:
        path = analysis["path"]
        if analysis["file_lines"] > max_file_lines:
            oversized_files.append({
                "path": path,
                "lines": analysis["file_lines"],
                "limit": max_file_lines,
            })
        for func in analysis["functions"]:
            if func["length"] > max_func_lines:
                oversized_functions.append({
                    "path": path,
                    "function": func["name"],
                    "line": func["line"],
                    "length": func["length"],
                    "limit": max_func_lines,
                })
            if func["nesting_depth"] > max_nesting_depth:
                deep_nesting.append({
                    "path": path,
                    "function": func["name"],
                    "line": func["line"],
                    "depth": func["nesting_depth"],
                    "limit": max_nesting_depth,
                })

    oversized_functions.sort(key=lambda x: -x["length"])
    deep_nesting.sort(key=lambda x: -x["depth"])
    oversized_files.sort(key=lambda x: -x["lines"])
    return {
        "oversized_files": oversized_files,
        "oversized_functions": oversized_functions,
        "deep_nesting": deep_nesting,
    }


def load_baseline(path):
    """Load a baseline file. Returns dict with suppressed violations, or empty structure."""
    if not path or not os.path.exists(path):
        return {"oversized_files": {}, "oversized_functions": {}, "deep_nesting": {}}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {
        "oversized_files": {e["path"]: e for e in data.get("oversized_files", [])},
        "oversized_functions": {e["key"]: e for e in data.get("oversized_functions", [])},
        "deep_nesting": {e["key"]: e for e in data.get("deep_nesting", [])},
    }


def save_baseline(path, violations):
    """Write current violations to a baseline file for future suppression."""
    data = {
        "oversized_files": [
            {"path": v["path"], "lines": v["lines"]}
            for v in violations["oversized_files"]
        ],
        "oversized_functions": [
            {"key": "{}::{}".format(v["path"], v["function"]),
             "path": v["path"], "function": v["function"], "length": v["length"]}
            for v in violations["oversized_functions"]
        ],
        "deep_nesting": [
            {"key": "{}::{}".format(v["path"], v["function"]),
             "path": v["path"], "function": v["function"], "depth": v["depth"]}
            for v in violations["deep_nesting"]
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def filter_violations_against_baseline(violations, baseline):
    """Remove violations that are in the baseline and haven't gotten worse.

    A suppressed violation reappears if:
    - oversized_function: length increased beyond baseline
    - oversized_file: lines increased beyond baseline
    - deep_nesting: depth increased beyond baseline
    """
    filtered_funcs = []
    for v in violations["oversized_functions"]:
        key = "{}::{}".format(v["path"], v["function"])
        entry = baseline["oversized_functions"].get(key)
        if entry and v["length"] <= entry["length"]:
            continue  # suppressed — same or better
        filtered_funcs.append(v)

    filtered_files = []
    for v in violations["oversized_files"]:
        entry = baseline["oversized_files"].get(v["path"])
        if entry and v["lines"] <= entry["lines"]:
            continue
        filtered_files.append(v)

    filtered_nesting = []
    for v in violations["deep_nesting"]:
        key = "{}::{}".format(v["path"], v["function"])
        entry = baseline["deep_nesting"].get(key)
        if entry and v["depth"] <= entry["depth"]:
            continue
        filtered_nesting.append(v)

    return {
        "oversized_files": filtered_files,
        "oversized_functions": filtered_funcs,
        "deep_nesting": filtered_nesting,
    }


def count_baselined(violations, filtered):
    """Count how many violations were suppressed by the baseline."""
    original = (
        len(violations["oversized_files"])
        + len(violations["oversized_functions"])
        + len(violations["deep_nesting"])
    )
    after = (
        len(filtered["oversized_files"])
        + len(filtered["oversized_functions"])
        + len(filtered["deep_nesting"])
    )
    return original - after


def format_markdown_report(violations, max_func_lines, max_file_lines, max_nesting_depth, baselined_count=0):
    """Format violations as a GitHub Issue-friendly markdown report."""
    total = (
        len(violations["oversized_files"])
        + len(violations["oversized_functions"])
        + len(violations["deep_nesting"])
    )

    if total == 0:
        return "## Code Health Check: All Clear\n\nNo violations found. All files and functions are within limits."

    lines = []
    lines.append("## Code Health Check: {} violation{} found\n".format(total, "s" if total != 1 else ""))
    lines.append("This is an automated report from the code health checker.")
    lines.append("The codebase guidelines recommend small, single-purpose functions ")
    lines.append("with flat control flow for agent-maintained code.\n")
    if baselined_count > 0:
        lines.append("_{} known violation{} suppressed by baseline. ".format(
            baselined_count, "s" if baselined_count != 1 else ""))
        lines.append("These will reappear if the code gets worse._\n")

    if violations["oversized_functions"]:
        lines.append("### Oversized Functions (limit: {} lines)\n".format(max_func_lines))
        lines.append("| Function | File | Line | Length | Over by |")
        lines.append("|----------|------|------|--------|---------|")
        for v in violations["oversized_functions"]:
            over = v["length"] - v["limit"]
            lines.append("| `{}` | {} | L{} | **{}** | +{} |".format(
                v["function"], v["path"], v["line"], v["length"], over
            ))
        lines.append("")

    if violations["oversized_files"]:
        lines.append("### Oversized Files (limit: {} lines)\n".format(max_file_lines))
        lines.append("| File | Lines | Over by |")
        lines.append("|------|-------|---------|")
        for v in violations["oversized_files"]:
            over = v["lines"] - v["limit"]
            lines.append("| {} | **{}** | +{} |".format(v["path"], v["lines"], over))
        lines.append("")

    if violations["deep_nesting"]:
        lines.append("### Excessive Nesting (limit: {} levels)\n".format(max_nesting_depth))
        lines.append("| Function | File | Line | Depth |")
        lines.append("|----------|------|------|-------|")
        for v in violations["deep_nesting"]:
            lines.append("| `{}` | {} | L{} | **{}** |".format(
                v["function"], v["path"], v["line"], v["depth"]
            ))
        lines.append("")

    lines.append("### Recommendations\n")
    lines.append("- Extract helper functions from oversized functions")
    lines.append("- Use early returns to flatten deep nesting")
    lines.append("- Split large files by extracting related helpers into new modules")
    lines.append("- Each function should do one thing with a clear name\n")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Code health checker for agent-maintained codebases")
    parser.add_argument("--src-dir", default=DEFAULT_SRC_DIR, help="Source directory to analyze")
    parser.add_argument("--max-func", type=int, default=DEFAULT_MAX_FUNC_LINES, help="Max function lines")
    parser.add_argument("--max-file", type=int, default=DEFAULT_MAX_FILE_LINES, help="Max file lines")
    parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_NESTING_DEPTH, help="Max nesting depth")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    parser.add_argument("--baseline", default=None,
                        help="Path to baseline JSON file. Suppresses known violations unless they get worse.")
    parser.add_argument("--update-baseline", action="store_true",
                        help="Write current violations to the baseline file and exit.")
    args = parser.parse_args()

    files = collect_files(args.src_dir)
    if not files:
        print("No Python files found in {}".format(args.src_dir), file=sys.stderr)
        sys.exit(1)

    analyses = [analyze_file(f) for f in files]
    violations = find_violations(analyses, args.max_func, args.max_file, args.max_depth)

    # Update baseline mode: write current violations and exit
    if args.update_baseline:
        baseline_path = args.baseline or DEFAULT_BASELINE_FILE
        save_baseline(baseline_path, violations)
        total = (
            len(violations["oversized_files"])
            + len(violations["oversized_functions"])
            + len(violations["deep_nesting"])
        )
        print("Baseline written to {} ({} violations recorded)".format(baseline_path, total))
        sys.exit(0)

    # Filter against baseline if provided
    baselined_count = 0
    if args.baseline:
        baseline = load_baseline(args.baseline)
        filtered = filter_violations_against_baseline(violations, baseline)
        baselined_count = count_baselined(violations, filtered)
        violations = filtered

    total = (
        len(violations["oversized_files"])
        + len(violations["oversized_functions"])
        + len(violations["deep_nesting"])
    )

    if args.format == "json":
        output = {
            "violations": violations,
            "summary": {
                "total_violations": total,
                "baselined_violations": baselined_count,
                "files_analyzed": len(files),
                "limits": {
                    "max_function_lines": args.max_func,
                    "max_file_lines": args.max_file,
                    "max_nesting_depth": args.max_depth,
                },
            },
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_markdown_report(violations, args.max_func, args.max_file, args.max_depth, baselined_count))

    # Exit with non-zero if violations found (useful for CI)
    if total > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
