"""Configuration constants for the multi-agent development orchestrator.

Language configurations for tree-sitter-based code analysis. Each entry maps
a language name to its grammar module, file extensions, and node type mappings
used by the analyzer in code_analysis.py.
"""

# ---------------------------------------------------------------------------
# Analysis thresholds (two-tier: advisory at warn, violation at hard)
# ---------------------------------------------------------------------------

ANALYSIS_THRESHOLDS = {
    "function_size": {"warn": 40, "hard": 60},
    "nesting_depth": {"warn": 4, "hard": 6},
    "cyclomatic_complexity": {"warn": 10, "hard": 15},
    "parameter_count": {"warn": 7, "hard": 10},
    "file_size": {"warn": 300, "hard": 500},
}


# ---------------------------------------------------------------------------
# Node type mappings per language
# ---------------------------------------------------------------------------

PYTHON_CONFIG = {
    "grammar_module": "tree_sitter_python",
    "language_func": "language",
    "file_extensions": {".py"},
    "function_types": {"function_definition"},
    "branching_types": {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "assert_statement",
        "boolean_operator",
        "conditional_expression",
    },
    "nesting_types": {
        "if_statement",
        "for_statement",
        "while_statement",
        "try_statement",
        "with_statement",
        "except_clause",
    },
    "parameter_node": "parameters",
    "self_names": {"self", "cls"},
    "import_types": {"import_statement", "import_from_statement"},
}

JAVASCRIPT_CONFIG = {
    "grammar_module": "tree_sitter_javascript",
    "language_func": "language",
    "file_extensions": {".js", ".jsx", ".mjs"},
    "function_types": {
        "function_declaration",
        "arrow_function",
        "method_definition",
        "function",
    },
    "branching_types": {
        "if_statement",
        "for_statement",
        "while_statement",
        "for_in_statement",
        "do_statement",
        "switch_case",
        "catch_clause",
        "ternary_expression",
    },
    "nesting_types": {
        "if_statement",
        "for_statement",
        "while_statement",
        "for_in_statement",
        "do_statement",
        "try_statement",
        "catch_clause",
    },
    "parameter_node": "formal_parameters",
    "self_names": set(),
    "import_types": {"import_statement"},
}

TYPESCRIPT_CONFIG = {
    "grammar_module": "tree_sitter_typescript",
    "language_func": "language_typescript",
    "file_extensions": {".ts"},
    "function_types": {
        "function_declaration",
        "arrow_function",
        "method_definition",
        "function",
    },
    "branching_types": {
        "if_statement",
        "for_statement",
        "while_statement",
        "for_in_statement",
        "do_statement",
        "switch_case",
        "catch_clause",
        "ternary_expression",
    },
    "nesting_types": {
        "if_statement",
        "for_statement",
        "while_statement",
        "for_in_statement",
        "do_statement",
        "try_statement",
        "catch_clause",
    },
    "parameter_node": "formal_parameters",
    "self_names": set(),
    "import_types": {"import_statement"},
}

TSX_CONFIG = {
    "grammar_module": "tree_sitter_typescript",
    "language_func": "language_tsx",
    "file_extensions": {".tsx"},
    "function_types": {
        "function_declaration",
        "arrow_function",
        "method_definition",
        "function",
    },
    "branching_types": {
        "if_statement",
        "for_statement",
        "while_statement",
        "for_in_statement",
        "do_statement",
        "switch_case",
        "catch_clause",
        "ternary_expression",
    },
    "nesting_types": {
        "if_statement",
        "for_statement",
        "while_statement",
        "for_in_statement",
        "do_statement",
        "try_statement",
        "catch_clause",
    },
    "parameter_node": "formal_parameters",
    "self_names": set(),
    "import_types": {"import_statement"},
}

CSHARP_CONFIG = {
    "grammar_module": "tree_sitter_c_sharp",
    "language_func": "language",
    "file_extensions": {".cs"},
    "function_types": {
        "method_declaration",
        "constructor_declaration",
        "local_function_statement",
    },
    "branching_types": {
        "if_statement",
        "for_statement",
        "while_statement",
        "for_each_statement",
        "do_statement",
        "switch_section",
        "catch_clause",
        "conditional_expression",
    },
    "nesting_types": {
        "if_statement",
        "for_statement",
        "while_statement",
        "for_each_statement",
        "do_statement",
        "try_statement",
        "catch_clause",
    },
    "parameter_node": "parameter_list",
    "self_names": set(),
    "import_types": {"using_directive"},
}


# ---------------------------------------------------------------------------
# Combined lookup: language name -> config dict
# ---------------------------------------------------------------------------

LANGUAGE_CONFIGS = {
    "python": PYTHON_CONFIG,
    "javascript": JAVASCRIPT_CONFIG,
    "typescript": TYPESCRIPT_CONFIG,
    "tsx": TSX_CONFIG,
    "csharp": CSHARP_CONFIG,
}
