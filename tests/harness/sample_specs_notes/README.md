# Notes App — Iterative Spec Set

Three spec files for testing the iterative `go` workflow. All three produce the
same final app (Express API + React UI with create and delete).

## Files

| File | Purpose |
|---|---|
| `sample_spec_notes_base.md` | Session 1: API + UI with list and add |
| `sample_spec_notes_add_delete.md` | Session 2 (delta): just the delete feature |
| `sample_spec_notes_full.md` | Session 2 (combined): everything in one file |

## Test paths

**Path A — incremental (new stuff only):**
```bash
# Session 1: build the base app
agentic-dev go --directory notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_base.md --local
# Session 2: resume and add the delete feature
agentic-dev go --directory notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_add_delete.md --local
```

**Path B — combined (full replacement):**
```bash
# Session 1: build the base app
agentic-dev go --directory notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_base.md --local
# Session 2: resume with the full combined spec
agentic-dev go --directory notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_full.md --local
```

**Using the test harness (Path A — incremental):**
```bash
# Session 1: build the base app
./tests/harness/run_test.sh --name notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_base.md
# Session 2: resume the latest run with the delta spec
./tests/harness/run_test.sh --name notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_add_delete.md --resume
```

**Using the test harness (Path B — combined):**
```bash
# Session 1: build the base app
./tests/harness/run_test.sh --name notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_base.md
# Session 2: resume the latest run with the full combined spec
./tests/harness/run_test.sh --name notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_full.md --resume
```

> **Note:** `--name` here is the harness's flag (names the directory inside `runs/<timestamp>/`).
> The harness passes `--directory` and `--local` to the CLI automatically.

Both paths should produce the same result: a notes app with list, add, and delete.
