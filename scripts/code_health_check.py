"""Code health checker for agent-maintained codebases.

Analyzes Python source files for:
- Functions exceeding a maximum line count
- Files exceeding a maximum line count
- Excessive nesting depth in functions

Outputs a structured report suitable for GitHub Issues.

Usage:
    python scripts/code_health_check.py [--src-dir src/agent] [--max-func 40] [--max-file 300] [--max-depth 4]
    python scripts/code_health_check.py --format json
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


def format_markdown_report(violations, max_func_lines, max_file_lines, max_nesting_depth):
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
    args = parser.parse_args()

    files = collect_files(args.src_dir)
    if not files:
        print("No Python files found in {}".format(args.src_dir), file=sys.stderr)
        sys.exit(1)

    analyses = [analyze_file(f) for f in files]
    violations = find_violations(analyses, args.max_func, args.max_file, args.max_depth)

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
        print(format_markdown_report(violations, args.max_func, args.max_file, args.max_depth))

    # Exit with non-zero if violations found (useful for CI)
    if total > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
