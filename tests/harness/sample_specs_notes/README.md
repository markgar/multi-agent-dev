# Notes App — Iterative Spec Set

Three spec files for testing the iterative `go` workflow. All three produce the
same final app (Express API + React UI with create and delete).

## Files

| File | Purpose |
|---|---|
| `sample_spec_notes_1_base.md` | Session 1: API + UI with list and add |
| `sample_spec_notes_2_add_delete.md` | Session 2 (delta): just the delete feature |
| `sample_spec_notes_full.md` | Combined: everything in one file |

## Test paths

### Direct CLI

Run `agentic-dev go` yourself — you manage the project directory.

**Path A — incremental (two sessions):**
```bash
# Session 1: build the base app
agentic-dev go --directory notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_1_base.md --local
# Session 2: resume and add the delete feature
agentic-dev go --directory notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_2_add_delete.md --local
```

**Path B — combined (single session):**
```bash
agentic-dev go --directory notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_full.md --local
```

---

### Test Harness

The harness creates a timestamped `runs/` directory, passes `--directory` and `--local` automatically, and supports `--resume` to find and continue the latest run.

> `--name` here is the harness's flag (names the subdirectory inside `runs/<timestamp>/`), not the CLI's `--name`.

**Path A — incremental (two sessions):**
```bash
# Session 1: build the base app
./tests/harness/run_test.sh --name notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_1_base.md
# Session 2: resume the latest run with the delta spec
./tests/harness/run_test.sh --name notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_2_add_delete.md --resume
```

**Path B — combined (single session):**
```bash
./tests/harness/run_test.sh --name notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_full.md
```

---

Both paths should produce the same result: a notes app with list, add, and delete.
