#!/bin/bash
# Test harness: runs a full end-to-end orchestration using a local bare git repo.
# Usage: ./tests/harness/run_test.sh [--spec-file path/to/spec.md] [--name project-name]
#
# Handles all setup automatically:
#   1. Cleans stale build/ artifacts
#   2. Installs the package in editable mode (pip install -e .)
#   3. Runs existing tests to catch problems early
#   4. Creates a timestamped run directory under tests/harness/runs/
#   5. Launches agentic-dev go --local
#   6. Prints log locations for post-mortem analysis

set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$HARNESS_DIR/../.." && pwd)"

# Defaults
SPEC_FILE="$HARNESS_DIR/sample_spec_cli_calculator.md"
PROJECT_NAME="test-run"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --spec-file)
            SPEC_FILE="$2"
            shift 2
            ;;
        --name)
            PROJECT_NAME="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--spec-file <path>] [--name <project>]"
            exit 1
            ;;
    esac
done

# Resolve spec file to absolute path
SPEC_FILE="$(cd "$(dirname "$SPEC_FILE")" && pwd)/$(basename "$SPEC_FILE")"
if [[ ! -f "$SPEC_FILE" ]]; then
    echo "ERROR: Spec file not found: $SPEC_FILE"
    exit 1
fi

# --- Pre-flight setup ---
echo "============================================"
echo " Pre-flight setup"
echo "============================================"

# Clean stale build artifacts
if [[ -d "$PROJECT_ROOT/build" ]]; then
    echo "  Removing stale build/ directory..."
    rm -rf "$PROJECT_ROOT/build"
fi

# Install package in editable mode
echo "  Installing package (pip install -e .)..."
pip install -e "$PROJECT_ROOT" --quiet 2>&1 | tail -1

# Verify the CLI is available
if ! command -v agentic-dev &> /dev/null; then
    echo "ERROR: agentic-dev not found on PATH after install."
    echo "Try: pip install -e $PROJECT_ROOT"
    exit 1
fi
echo "  ✓ agentic-dev is available"

# Run existing tests
echo "  Running unit tests..."
if ! python -m pytest "$PROJECT_ROOT/tests/" -q 2>&1 | tail -3; then
    echo ""
    echo "ERROR: Unit tests failed. Fix them before running the harness."
    exit 1
fi
echo ""

# --- Run ---
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="$HARNESS_DIR/runs/$TIMESTAMP"
mkdir -p "$RUN_DIR"

echo "============================================"
echo " Test Harness Run"
echo "============================================"
echo "  Run dir:    $RUN_DIR"
echo "  Spec file:  $SPEC_FILE"
echo "  Project:     $PROJECT_NAME"
echo "============================================"
echo ""

# Run from the timestamped directory
cd "$RUN_DIR"

agentic-dev go \
    --name "$PROJECT_NAME" \
    --spec-file "$SPEC_FILE" \
    --local

EXIT_CODE=$?

echo ""
echo "============================================"
echo " Run complete (exit code: $EXIT_CODE)"
echo "============================================"
echo "  Logs:       $RUN_DIR/$PROJECT_NAME/logs/"
echo "  Builder:    $RUN_DIR/$PROJECT_NAME/builder/"
echo "  Reviewer:   $RUN_DIR/$PROJECT_NAME/reviewer/"
echo "  Tester:     $RUN_DIR/$PROJECT_NAME/tester/"
echo "  Validator:  $RUN_DIR/$PROJECT_NAME/validator/"
echo "  Bare repo:  $RUN_DIR/$PROJECT_NAME/remote.git/"
echo "============================================"

exit $EXIT_CODE
