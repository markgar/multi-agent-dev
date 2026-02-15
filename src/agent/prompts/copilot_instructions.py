"""Copilot instructions template and generation prompt."""

COPILOT_INSTRUCTIONS_TEMPLATE = """\
# Copilot Instructions

## About this codebase

This software is written with assistance from GitHub Copilot. The code is structured \
to be readable, modifiable, and extendable by Copilot (and other LLM-based agents). \
Every design decision should reinforce that.

### Guidelines for LLM-friendly code

- **Flat, explicit control flow.** Prefer straightforward if/else and early returns \
over deeply nested logic, complex inheritance hierarchies, or metaprogramming. Every \
function should be understandable from its source alone.
- **Small, single-purpose functions.** Keep functions short (ideally under ~40 lines). \
Each function does one thing with a clear name that describes it. This gives the LLM \
better context boundaries.
- **Descriptive naming over comments.** Variable and function names should make intent \
obvious. Use comments only when *why* isn't clear from the code — never to explain *what*.
- **Colocate related logic.** Keep constants, helpers, and the code that uses them close \
together (or in the same small file). Avoid scattering related pieces across many \
modules — LLMs work best when relevant context is nearby.
- **Consistent patterns.** When multiple functions do similar things, structure them \
identically. Consistent shape lets the LLM reliably extend the pattern.
- **No magic.** Avoid decorators that hide behavior, dynamic attribute access, implicit \
registration, or monkey-patching. Everything should be traceable by reading the code \
top-to-bottom.
- **Graceful error handling.** Wrap I/O and external calls in try/except (or the \
language's equivalent). Never let a transient failure crash the main workflow. Log the \
error and continue.
- **Minimal dependencies.** Only add a dependency when it provides substantial value. \
Fewer deps mean less surface area for the LLM to misunderstand.
- **One concept per file.** Each module owns a single concern. Don't mix unrelated \
responsibilities in the same file.
- **Design for testability.** Separate pure decision logic from I/O and subprocess calls \
so core functions can be tested without mocking. Pass dependencies as arguments rather \
than hard-coding them inside functions when practical. Keep side-effect-free helpers \
(parsing, validation, data transforms) in their own functions so they can be unit tested \
directly.

### Documentation maintenance

- When completing a task that changes the project structure, key files, architecture, or \
conventions, update `.github/copilot-instructions.md` to reflect the change.
- Keep the project-specific sections (Project structure, Key files, Architecture, \
Conventions) accurate and current.
- Never modify the coding guidelines or testing conventions sections above.
- This file is a **style guide**, not a spec. Describe file **roles** (e.g. 'server \
entry point'), not implementation details (e.g. 'uses List<T> with auto-incrementing IDs'). \
Conventions describe coding **patterns** (e.g. 'consistent JSON error envelope'), not \
implementation choices (e.g. 'store data in a static variable'). SPEC.md covers what to \
build — this file covers how to write code that fits the project.

## Project structure

{project_structure}

## Key files

{key_files}

## Architecture

{architecture}

## Testing conventions

- **Use the project's test framework.** Plain functions with descriptive names.
- **Test the contract, not the implementation.** A test should describe expected behavior \
in terms a user would understand — not mirror the code's internal branching. If the test \
would break when you refactor internals without changing behavior, it's too tightly coupled.
- **Name tests as behavioral expectations.** `test_expired_token_triggers_refresh` not \
`test_check_token_returns_false`. The test name should read like a requirement.
- **Use realistic inputs.** Feed real-looking data, not minimal one-line synthetic strings. \
Edge cases should be things that could actually happen — corrupted inputs, empty files, \
missing fields.
- **Prefer regression tests.** When a bug is found, write the test that would have caught \
it before fixing it. This is the highest-value test you can write.
- **Don't test I/O wrappers.** Functions that just read a file and call a pure helper \
don't need their own tests — test the pure helper directly.
- **No mocking unless unavoidable.** Extract pure functions for testability so you don't \
need mocks. If you find yourself mocking, consider whether you should be testing a \
different function.

## Conventions

{conventions}
"""

COPILOT_INSTRUCTIONS_PROMPT = (
    "You are a documentation generator. You must NOT write any application code or "
    "modify any source files other than .github/copilot-instructions.md. "
    "Read SPEC.md to understand the tech stack, language, and architecture. "
    "Read TASKS.md to understand the planned components and milestones. "
    "Read REQUIREMENTS.md for the original project intent. "
    "Now create the file .github/copilot-instructions.md (create the .github directory "
    "if it doesn't exist). The file must follow this EXACT template — do not change the "
    "coding guidelines or testing conventions sections. Only fill in the project-specific "
    "sections:\n\n"
    "For 'Project structure': describe the directory layout based on the tech stack. "
    "Example: 'Source code lives in `src/` — this is the primary directory to edit.'\n\n"
    "For 'Key files': list ONLY files that exist in the repo right now — run `find` or "
    "`ls` to check. Do NOT predict files from the roadmap or unstarted milestones. After "
    "bootstrap, this is typically just the project file, entry point, and config (~5 "
    "entries). The builder will update this section as files are created.\n\n"
    "For 'Architecture': 3-5 sentences about how layers communicate — major components, "
    "data flow, dependency direction. Do NOT list entities, directories, or API routes. "
    "Do NOT repeat SPEC.md content.\n\n"
    "For 'Conventions': list coding STYLE and PATTERN conventions — things like API "
    "response format, error handling approach, naming patterns. "
    "GOOD: 'Thin controllers delegate to application services', 'All API responses use "
    "a consistent JSON error envelope', 'Fluent API only for EF Core configuration'. "
    "BAD: 'Cookie-based auth using HttpOnly cookies' (architectural decision — belongs "
    "in SPEC.md), 'Auto-generated TypeScript API client from OpenAPI' (architectural "
    "decision — belongs in SPEC.md), 'Entity configurations live in "
    "Infrastructure/Data/Configurations/' (file location prediction — builder decides "
    "this). Do NOT include architectural decisions or file location predictions.\n\n"
    "IMPORTANT: This file is a STYLE GUIDE, not a spec or blueprint. It should help "
    "the builder write code that fits the project's patterns, NOT tell the builder what "
    "code to write. SPEC.md and TASKS.md already do that. If you find yourself "
    "describing data structures, specific classes, or where to put specific logic, "
    "you've gone too far — pull back to the pattern level.\n\n"
    "Here is the template to use:\n\n"
    "{template}\n\n"
    "Fill in the placeholder sections (project_structure, key_files, architecture, "
    "conventions) with project-specific content derived from SPEC.md, TASKS.md, and "
    "REQUIREMENTS.md. Keep the coding guidelines, documentation maintenance, and "
    "testing conventions sections exactly as they are in the template. "
    "Commit with message '[planner] Add copilot instructions', run git pull --rebase, and push."
)
