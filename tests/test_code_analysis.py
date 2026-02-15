"""Tests for tree-sitter-based code analysis."""

import importlib

import pytest
from tree_sitter import Language, Parser

from agentic_dev.code_analysis import (
    Finding,
    analyze_source,
    classify_severity,
    config_for_file,
    count_parameters,
    find_functions,
    format_findings,
    get_function_name,
    measure_cyclomatic_complexity,
    measure_function_size,
    measure_nesting_depth,
)
from agentic_dev.config import (
    CSHARP_CONFIG,
    JAVASCRIPT_CONFIG,
    LANGUAGE_CONFIGS,
    PYTHON_CONFIG,
    TYPESCRIPT_CONFIG,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_parser(config):
    """Create a parser from a language config."""
    mod = importlib.import_module(config["grammar_module"])
    func = getattr(mod, config["language_func"])
    language = Language(func())
    return Parser(language)


def _parse(source, config):
    """Parse source code and return the root node."""
    parser = _make_parser(config)
    tree = parser.parse(bytes(source, "utf8"))
    return tree.root_node


def _first_function(root, config):
    """Return the first function node found in a tree."""
    funcs = find_functions(root, config["function_types"])
    assert funcs, "No function found in source"
    return funcs[0]


def _make_finding(**kwargs):
    """Create a Finding with sensible defaults."""
    defaults = {
        "file": "test.py",
        "line": 1,
        "function_name": "foo",
        "check": "function_size",
        "value": 50,
        "warn_threshold": 40,
        "hard_threshold": 60,
        "severity": "advisory",
    }
    defaults.update(kwargs)
    return Finding(**defaults)


# ---------------------------------------------------------------------------
# classify_severity
# ---------------------------------------------------------------------------


def test_classify_below_warn_returns_none():
    assert classify_severity(5, 10, 20) is None


def test_classify_at_warn_returns_advisory():
    assert classify_severity(10, 10, 20) == "advisory"


def test_classify_between_warn_and_hard_returns_advisory():
    assert classify_severity(15, 10, 20) == "advisory"


def test_classify_at_hard_returns_violation():
    assert classify_severity(20, 10, 20) == "violation"


def test_classify_above_hard_returns_violation():
    assert classify_severity(30, 10, 20) == "violation"


# ---------------------------------------------------------------------------
# measure_function_size — Python
# ---------------------------------------------------------------------------


def test_small_python_function_size():
    source = "def foo():\n    return 1\n"
    root = _parse(source, PYTHON_CONFIG)
    func = _first_function(root, PYTHON_CONFIG)
    assert measure_function_size(func) == 2


def test_multiline_python_function_size():
    lines = ["def foo():"] + [f"    x = {i}" for i in range(20)] + ["    return x\n"]
    source = "\n".join(lines)
    root = _parse(source, PYTHON_CONFIG)
    func = _first_function(root, PYTHON_CONFIG)
    assert measure_function_size(func) == 22


# ---------------------------------------------------------------------------
# measure_nesting_depth — Python
# ---------------------------------------------------------------------------


def test_flat_python_function_has_zero_nesting():
    source = "def foo():\n    return 1\n"
    root = _parse(source, PYTHON_CONFIG)
    func = _first_function(root, PYTHON_CONFIG)
    assert measure_nesting_depth(func, PYTHON_CONFIG["nesting_types"]) == 0


def test_nested_python_if_for_has_depth_two():
    source = (
        "def foo(items):\n"
        "    if items:\n"
        "        for item in items:\n"
        "            print(item)\n"
    )
    root = _parse(source, PYTHON_CONFIG)
    func = _first_function(root, PYTHON_CONFIG)
    assert measure_nesting_depth(func, PYTHON_CONFIG["nesting_types"]) == 2


# ---------------------------------------------------------------------------
# measure_cyclomatic_complexity — Python
# ---------------------------------------------------------------------------


def test_simple_python_function_has_complexity_one():
    source = "def foo():\n    return 1\n"
    root = _parse(source, PYTHON_CONFIG)
    func = _first_function(root, PYTHON_CONFIG)
    assert measure_cyclomatic_complexity(func, PYTHON_CONFIG["branching_types"]) == 1


def test_python_function_with_branches_has_higher_complexity():
    source = (
        "def foo(x):\n"
        "    if x > 0:\n"
        "        return 1\n"
        "    elif x < 0:\n"
        "        return -1\n"
        "    else:\n"
        "        return 0\n"
    )
    root = _parse(source, PYTHON_CONFIG)
    func = _first_function(root, PYTHON_CONFIG)
    # 1 base + at least 2 branches (if + elif)
    assert measure_cyclomatic_complexity(func, PYTHON_CONFIG["branching_types"]) >= 3


# ---------------------------------------------------------------------------
# count_parameters — Python
# ---------------------------------------------------------------------------


def test_python_method_excludes_self():
    source = (
        "class Foo:\n"
        "    def bar(self, a, b):\n"
        "        pass\n"
    )
    root = _parse(source, PYTHON_CONFIG)
    func = _first_function(root, PYTHON_CONFIG)
    assert count_parameters(func, PYTHON_CONFIG["parameter_node"], PYTHON_CONFIG["self_names"]) == 2


def test_python_standalone_function_counts_all():
    source = "def foo(a, b, c):\n    pass\n"
    root = _parse(source, PYTHON_CONFIG)
    func = _first_function(root, PYTHON_CONFIG)
    assert count_parameters(func, PYTHON_CONFIG["parameter_node"], PYTHON_CONFIG["self_names"]) == 3


def test_python_no_params_returns_zero():
    source = "def foo():\n    pass\n"
    root = _parse(source, PYTHON_CONFIG)
    func = _first_function(root, PYTHON_CONFIG)
    assert count_parameters(func, PYTHON_CONFIG["parameter_node"], PYTHON_CONFIG["self_names"]) == 0


# ---------------------------------------------------------------------------
# get_function_name
# ---------------------------------------------------------------------------


def test_python_function_name():
    source = "def my_func():\n    pass\n"
    root = _parse(source, PYTHON_CONFIG)
    func = _first_function(root, PYTHON_CONFIG)
    assert get_function_name(func) == "my_func"


# ---------------------------------------------------------------------------
# JavaScript tests
# ---------------------------------------------------------------------------


def test_javascript_function_size():
    source = "function hello() {\n  return 1;\n}\n"
    root = _parse(source, JAVASCRIPT_CONFIG)
    func = _first_function(root, JAVASCRIPT_CONFIG)
    assert measure_function_size(func) == 3


def test_javascript_arrow_function_detected():
    source = "const foo = (a, b) => {\n  return a + b;\n};\n"
    root = _parse(source, JAVASCRIPT_CONFIG)
    funcs = find_functions(root, JAVASCRIPT_CONFIG["function_types"])
    assert len(funcs) >= 1


def test_javascript_nesting():
    source = (
        "function process(items) {\n"
        "  if (items.length > 0) {\n"
        "    for (let i = 0; i < items.length; i++) {\n"
        "      console.log(items[i]);\n"
        "    }\n"
        "  }\n"
        "}\n"
    )
    root = _parse(source, JAVASCRIPT_CONFIG)
    func = _first_function(root, JAVASCRIPT_CONFIG)
    assert measure_nesting_depth(func, JAVASCRIPT_CONFIG["nesting_types"]) == 2


def test_javascript_parameter_count():
    source = "function foo(a, b, c, d) {\n  return a;\n}\n"
    root = _parse(source, JAVASCRIPT_CONFIG)
    func = _first_function(root, JAVASCRIPT_CONFIG)
    assert count_parameters(func, JAVASCRIPT_CONFIG["parameter_node"], JAVASCRIPT_CONFIG["self_names"]) == 4


# ---------------------------------------------------------------------------
# C# tests
# ---------------------------------------------------------------------------


def test_csharp_method_size():
    source = (
        "public class Foo {\n"
        "  public void Bar() {\n"
        "    return;\n"
        "  }\n"
        "}\n"
    )
    root = _parse(source, CSHARP_CONFIG)
    func = _first_function(root, CSHARP_CONFIG)
    assert measure_function_size(func) >= 3


def test_csharp_parameter_count():
    source = (
        "public class Foo {\n"
        "  public void Bar(int a, string b, bool c) {\n"
        "    return;\n"
        "  }\n"
        "}\n"
    )
    root = _parse(source, CSHARP_CONFIG)
    func = _first_function(root, CSHARP_CONFIG)
    assert count_parameters(func, CSHARP_CONFIG["parameter_node"], CSHARP_CONFIG["self_names"]) == 3


def test_csharp_nesting_depth():
    source = (
        "public class Foo {\n"
        "  public void Bar() {\n"
        "    if (true) {\n"
        "      while (true) {\n"
        "        try {\n"
        "        } catch (Exception e) {\n"
        "        }\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
    )
    root = _parse(source, CSHARP_CONFIG)
    func = _first_function(root, CSHARP_CONFIG)
    depth = measure_nesting_depth(func, CSHARP_CONFIG["nesting_types"])
    assert depth >= 3


def test_csharp_function_name():
    source = (
        "public class Foo {\n"
        "  public void ProcessOrder() {\n"
        "    return;\n"
        "  }\n"
        "}\n"
    )
    root = _parse(source, CSHARP_CONFIG)
    func = _first_function(root, CSHARP_CONFIG)
    assert get_function_name(func) == "ProcessOrder"


# ---------------------------------------------------------------------------
# TypeScript tests
# ---------------------------------------------------------------------------


def test_typescript_function_detected():
    source = "function greet(name: string): string {\n  return name;\n}\n"
    root = _parse(source, TYPESCRIPT_CONFIG)
    funcs = find_functions(root, TYPESCRIPT_CONFIG["function_types"])
    assert len(funcs) >= 1


def test_typescript_function_size():
    source = "function greet(name: string): string {\n  return name;\n}\n"
    root = _parse(source, TYPESCRIPT_CONFIG)
    func = _first_function(root, TYPESCRIPT_CONFIG)
    assert measure_function_size(func) == 3


# ---------------------------------------------------------------------------
# config_for_file
# ---------------------------------------------------------------------------


def test_config_for_python_file():
    config = config_for_file("app/main.py")
    assert config is not None
    assert ".py" in config["file_extensions"]


def test_config_for_javascript_file():
    config = config_for_file("src/index.js")
    assert config is not None
    assert ".js" in config["file_extensions"]


def test_config_for_typescript_file():
    config = config_for_file("src/app.ts")
    assert config is not None
    assert ".ts" in config["file_extensions"]


def test_config_for_tsx_file():
    config = config_for_file("src/App.tsx")
    assert config is not None
    assert ".tsx" in config["file_extensions"]


def test_config_for_csharp_file():
    config = config_for_file("Controllers/HomeController.cs")
    assert config is not None
    assert ".cs" in config["file_extensions"]


def test_config_for_unknown_extension():
    assert config_for_file("README.md") is None


def test_config_for_no_extension():
    assert config_for_file("Dockerfile") is None


# ---------------------------------------------------------------------------
# analyze_source — integration
# ---------------------------------------------------------------------------


def test_analyze_source_finds_large_python_function():
    body = "\n".join(f"    x_{i} = {i}" for i in range(65))
    source = f"def big_func():\n{body}\n    return x_0\n"
    findings = analyze_source(source, PYTHON_CONFIG, "app.py")
    size_findings = [f for f in findings if f.check == "function_size"]
    assert len(size_findings) == 1
    assert size_findings[0].severity == "violation"
    assert size_findings[0].value >= 60


def test_analyze_source_clean_python_produces_no_function_findings():
    source = "def foo(a):\n    return a + 1\n"
    findings = analyze_source(source, PYTHON_CONFIG, "clean.py")
    func_findings = [f for f in findings if f.function_name != "<file>"]
    assert func_findings == []


def test_analyze_source_large_file_produces_file_size_finding():
    lines = [f"x_{i} = {i}" for i in range(350)]
    source = "\n".join(lines)
    findings = analyze_source(source, PYTHON_CONFIG, "big_file.py")
    file_findings = [f for f in findings if f.check == "file_size"]
    assert len(file_findings) == 1
    assert file_findings[0].severity == "advisory"


def test_analyze_source_empty_string_returns_no_function_findings():
    findings = analyze_source("", PYTHON_CONFIG, "empty.py")
    func_findings = [f for f in findings if f.function_name != "<file>"]
    assert func_findings == []


def test_analyze_source_finds_large_javascript_function():
    body = "\n".join(f"  let x_{i} = {i};" for i in range(65))
    source = f"function bigFunc() {{\n{body}\n  return x_0;\n}}\n"
    findings = analyze_source(source, JAVASCRIPT_CONFIG, "app.js")
    size_findings = [f for f in findings if f.check == "function_size"]
    assert len(size_findings) == 1
    assert size_findings[0].severity == "violation"


def test_analyze_source_finds_large_csharp_method():
    body = "\n".join(f"    var x{i} = {i};" for i in range(65))
    source = (
        "public class Foo {\n"
        f"  public void BigMethod() {{\n{body}\n  }}\n"
        "}\n"
    )
    findings = analyze_source(source, CSHARP_CONFIG, "Foo.cs")
    size_findings = [f for f in findings if f.check == "function_size"]
    assert len(size_findings) >= 1
    assert any(f.severity == "violation" for f in size_findings)


# ---------------------------------------------------------------------------
# format_findings
# ---------------------------------------------------------------------------


def test_format_no_findings_returns_clean_message():
    result = format_findings([])
    assert "No structural issues" in result


def test_format_violations_appear_before_advisories():
    findings = [
        _make_finding(severity="advisory", file="a.py", line=1),
        _make_finding(severity="violation", file="b.py", line=1),
    ]
    result = format_findings(findings)
    lines = result.strip().split("\n")
    assert "[violation]" in lines[0]
    assert "[advisory]" in lines[1]


def test_format_caps_at_max():
    findings = [_make_finding(line=i) for i in range(30)]
    result = format_findings(findings, max_findings=5)
    lines = result.strip().split("\n")
    assert len(lines) == 6  # 5 findings + "... and 25 more"
    assert "25 more" in lines[-1]


def test_format_single_finding_includes_all_fields():
    findings = [
        _make_finding(
            file="src/app.py",
            line=42,
            function_name="process",
            check="function_size",
            value=75,
            warn_threshold=40,
            hard_threshold=60,
            severity="violation",
        )
    ]
    result = format_findings(findings)
    assert "src/app.py:42" in result
    assert "process" in result
    assert "function_size" in result
    assert "75" in result
    assert "40/60" in result


# ---------------------------------------------------------------------------
# All language configs have required keys
# ---------------------------------------------------------------------------


def test_all_language_configs_have_required_keys():
    required_keys = {
        "grammar_module",
        "language_func",
        "file_extensions",
        "function_types",
        "branching_types",
        "nesting_types",
        "parameter_node",
        "self_names",
        "import_types",
    }
    for name, config in LANGUAGE_CONFIGS.items():
        missing = required_keys - set(config.keys())
        assert not missing, f"Config '{name}' missing keys: {missing}"
