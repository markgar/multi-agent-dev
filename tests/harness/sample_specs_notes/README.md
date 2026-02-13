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
agentic-dev go --name notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_base.md --local
# ...later...
agentic-dev go --name notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_add_delete.md
```

**Path B — combined (full replacement):**
```bash
agentic-dev go --name notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_base.md --local
# ...later...
agentic-dev go --name notes-app --spec-file tests/harness/sample_specs_notes/sample_spec_notes_full.md
```

Both paths should produce the same result: a notes app with list, add, and delete.
