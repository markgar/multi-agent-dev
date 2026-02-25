#!/bin/bash
# Test harness: runs a full end-to-end orchestration using a local bare git repo.
# Usage: ./tests/harness/run_test.sh [--spec-file path/to/spec.md] [--name project-name] [--resume]
#
# Handles all setup automatically:
#   1. Cleans stale build/ artifacts
#   2. Installs the package in editable mode (pip install -e .)
#   3. Runs existing tests to catch problems early
#   4. Creates a timestamped run directory under tests/harness/runs/
#   5. Launches agentic-dev go --local
#   6. Prints log locations for post-mortem analysis
#
# Resume mode (--resume):
#   Instead of creating a new run, finds the latest existing run with the
#   given --name and resumes it via --directory. Deletes agent clone directories
#   (builder/, reviewer/, tester/, validator/) to simulate starting on a fresh
#   machine with only the repo available — matching production behavior against
#   GitHub. Optionally accepts a new --spec-file to add requirements.

set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$HARNESS_DIR/../.." && pwd)"

resolve_python_cmd() {
    if [[ -x "$PROJECT_ROOT/.venv/Scripts/python.exe" ]]; then
        echo "$PROJECT_ROOT/.venv/Scripts/python.exe"
        return
    fi
    if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
        echo "$PROJECT_ROOT/.venv/bin/python"
        return
    fi
    if command -v python >/dev/null 2>&1; then
        echo "python"
        return
    fi
    if command -v python3 >/dev/null 2>&1; then
        echo "python3"
        return
    fi
    echo ""
}

resolve_agentic_dev_cmd() {
    if command -v agentic-dev >/dev/null 2>&1; then
        echo "agentic-dev"
        return
    fi
    if [[ -x "$PROJECT_ROOT/.venv/Scripts/agentic-dev.exe" ]]; then
        echo "$PROJECT_ROOT/.venv/Scripts/agentic-dev.exe"
        return
    fi
    if [[ -x "$PROJECT_ROOT/.venv/bin/agentic-dev" ]]; then
        echo "$PROJECT_ROOT/.venv/bin/agentic-dev"
        return
    fi
    echo ""
}

to_python_path() {
    local input_path="$1"
    if [[ "$PYTHON_CMD" == *.exe ]] && command -v cygpath >/dev/null 2>&1; then
        cygpath -w "$input_path"
        return
    fi
    echo "$input_path"
}

# Defaults
SPEC_FILE=""
SPEC_FILE_DEFAULT="$HARNESS_DIR/sample_spec_cli_calculator.md"
SPEC_FILE_EXPLICIT=false
PROJECT_NAME=""
RESUME=false
MODEL=""
BUILDERS=1

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --spec-file)
            SPEC_FILE="$2"
            SPEC_FILE_EXPLICIT=true
            shift 2
            ;;
        --name)
            PROJECT_NAME="$2"
            shift 2
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        --resume)
            RESUME=true
            shift
            ;;
        --builders)
            BUILDERS="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--spec-file <path>] [--name <project>] [--model <model>] [--builders <N>] [--resume]"
            exit 1
            ;;
    esac
done

# --- Require --model ---
if [[ -z "$MODEL" ]]; then
    echo "ERROR: --model is required."
    echo "Allowed models: gpt-5.3-codex, claude-opus-4.6, claude-opus-4.6-fast"
    echo "Usage: $0 --model 'gpt-5.3-codex' [--spec-file <path>] [--name <project>] [--resume]"
    exit 1
fi

# --- Require --name ---
if [[ -z "$PROJECT_NAME" ]]; then
    echo "ERROR: --name is required."
    echo "Usage: $0 --name 'my-project' --model 'claude-opus-4.6' [--spec-file <path>] [--builders <N>] [--resume]"
    exit 1
fi

# --- Resolve spec file ---
# For fresh runs: use the default spec if none was explicitly provided.
# For resume: only use a spec if the user explicitly passed --spec-file.
if [[ "$RESUME" == false ]]; then
    if [[ -z "$SPEC_FILE" ]]; then
        SPEC_FILE="$SPEC_FILE_DEFAULT"
    fi
    SPEC_FILE="$(cd "$(dirname "$SPEC_FILE")" && pwd)/$(basename "$SPEC_FILE")"
    if [[ ! -f "$SPEC_FILE" ]]; then
        echo "ERROR: Spec file not found: $SPEC_FILE"
        exit 1
    fi
fi

# --- Pre-flight setup ---
echo "============================================"
echo " Pre-flight setup"
echo "============================================"

PYTHON_CMD="$(resolve_python_cmd)"
if [[ -z "$PYTHON_CMD" ]]; then
    echo "ERROR: Could not find Python."
    echo "Install Python or create a .venv in $PROJECT_ROOT"
    exit 1
fi

PROJECT_ROOT_FOR_PYTHON="$(to_python_path "$PROJECT_ROOT")"
TESTS_DIR_FOR_PYTHON="$(to_python_path "$PROJECT_ROOT/tests/")"

# Clean stale build artifacts
if [[ -d "$PROJECT_ROOT/build" ]]; then
    echo "  Removing stale build/ directory..."
    rm -rf "$PROJECT_ROOT/build"
fi

# Install package in editable mode
echo "  Installing package (pip install -e .)..."
"$PYTHON_CMD" -m pip install -e "$PROJECT_ROOT_FOR_PYTHON" --quiet 2>&1 | tail -1

# Verify the CLI is available
AGENTIC_DEV_CMD="$(resolve_agentic_dev_cmd)"
if [[ -z "$AGENTIC_DEV_CMD" ]]; then
    echo "ERROR: agentic-dev not found on PATH after install."
    echo "Try: $PYTHON_CMD -m pip install -e $PROJECT_ROOT"
    exit 1
fi
echo "  ✓ agentic-dev is available"

# Run existing tests
echo "  Running unit tests..."
if ! "$PYTHON_CMD" -m pytest "$TESTS_DIR_FOR_PYTHON" -q 2>&1 | tail -3; then
    echo ""
    echo "ERROR: Unit tests failed. Fix them before running the harness."
    exit 1
fi
echo ""

# --- Run ---
if [[ "$RESUME" == true ]]; then
    # Find all run directories for this project name (newest first)
    # Search by remote.git (the repo) rather than builder/ (agent clone)
    # so we can find runs even after agent dirs have been deleted.
    MATCHING_RUNS=()
    for ts_dir in $(ls -1dr "$HARNESS_DIR/runs/"* 2>/dev/null); do
        candidate="$ts_dir/$PROJECT_NAME"
        if [[ -d "$candidate/remote.git" ]]; then
            MATCHING_RUNS+=("$candidate")
        fi
    done

    if [[ ${#MATCHING_RUNS[@]} -eq 0 ]]; then
        echo "ERROR: No existing run found for project '$PROJECT_NAME'."
        echo ""
        echo "Available runs in $HARNESS_DIR/runs/:"
        ls -1d "$HARNESS_DIR/runs/"*/* 2>/dev/null | while read -r d; do
            if [[ -d "$d/remote.git" ]]; then echo "  $d"; fi
        done || echo "  (none found)"
        exit 1
    elif [[ ${#MATCHING_RUNS[@]} -eq 1 ]]; then
        PROJ_DIR="${MATCHING_RUNS[0]}"
    else
        echo ""
        echo "Multiple runs found for '$PROJECT_NAME':"
        echo ""
        for i in "${!MATCHING_RUNS[@]}"; do
            RUN_TS="$(basename "$(dirname "${MATCHING_RUNS[$i]}")")"
            MARKER=""
            if [[ $i -eq 0 ]]; then MARKER=" (latest)"; fi
            echo "  $((i + 1))) $RUN_TS$MARKER"
        done
        echo ""
        read -rp "Which run? [1] " PICK
        PICK="${PICK:-1}"
        if ! [[ "$PICK" =~ ^[0-9]+$ ]] || [[ "$PICK" -lt 1 ]] || [[ "$PICK" -gt ${#MATCHING_RUNS[@]} ]]; then
            echo "Invalid selection."
            exit 1
        fi
        PROJ_DIR="${MATCHING_RUNS[$((PICK - 1))]}"
    fi

    echo "============================================"
    echo " Resuming existing run"
    echo "============================================"
    echo "  Directory:  $PROJ_DIR"
    echo "  Project:    $PROJECT_NAME"
    if [[ -n "${SPEC_FILE:-}" && -f "${SPEC_FILE:-}" ]]; then
        echo "  New spec:   $SPEC_FILE"
    fi
    echo "============================================"
    echo ""

    # Delete agent clone directories to simulate a fresh machine.
    # Keep remote.git (the repo) and logs/ (checkpoints) intact.
    for agent_dir in builder reviewer tester validator; do
        if [[ -d "$PROJ_DIR/$agent_dir" ]]; then
            echo "  Removing $agent_dir/..."
            rm -rf "$PROJ_DIR/$agent_dir"
        fi
    done
    # Also remove numbered builder directories (builder-1, builder-2, ...)
    for builder_dir in "$PROJ_DIR"/builder-*; do
        if [[ -d "$builder_dir" ]]; then
            echo "  Removing $(basename "$builder_dir")/..."
            rm -rf "$builder_dir"
        fi
    done
    echo ""

    GO_ARGS=(--directory "$PROJ_DIR" --model "$MODEL" --local --builders "$BUILDERS")
    if [[ "$SPEC_FILE_EXPLICIT" == true && -n "${SPEC_FILE:-}" && -f "${SPEC_FILE:-}" ]]; then
        GO_ARGS+=(--spec-file "$SPEC_FILE")
    fi

    "$AGENTIC_DEV_CMD" go "${GO_ARGS[@]}"
    EXIT_CODE=$?
else
    # Fresh run: create new timestamped directory
    TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
    RUN_DIR="$HARNESS_DIR/runs/$TIMESTAMP"
    PROJ_DIR="$RUN_DIR/$PROJECT_NAME"

    echo "============================================"
    echo " Test Harness Run"
    echo "============================================"
    echo "  Run dir:    $RUN_DIR"
    echo "  Spec file:  $SPEC_FILE"
    echo "  Project:    $PROJECT_NAME"
    echo "============================================"
    echo ""

    mkdir -p "$RUN_DIR"

    "$AGENTIC_DEV_CMD" go \
        --directory "$PROJ_DIR" \
        --model "$MODEL" \
        --spec-file "$SPEC_FILE" \
        --builders "$BUILDERS" \
        --local

    EXIT_CODE=$?
fi

echo ""
echo "============================================"
echo " Run complete (exit code: $EXIT_CODE)"
echo "============================================"
echo "  Logs:       $PROJ_DIR/logs/"
echo "  Builder:    $PROJ_DIR/builder/"
echo "  Reviewer:   $PROJ_DIR/reviewer/"
echo "  Tester:     $PROJ_DIR/tester/"
echo "  Validator:  $PROJ_DIR/validator/"
if [[ -d "$PROJ_DIR/remote.git" ]]; then
    echo "  Bare repo:  $PROJ_DIR/remote.git/"
fi
echo "============================================"

exit $EXIT_CODE
