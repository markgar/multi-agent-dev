#!/bin/bash
# Test harness: runs a full end-to-end orchestration using a local bare git repo.
# Usage: ./tests/harness/run_test.sh [--spec-file path/to/spec.md] [--language node|python|dotnet]
#
# Creates a timestamped run directory under tests/harness/runs/ and launches
# agentic-dev go --local inside it. All logs end up under
# tests/harness/runs/<timestamp>/<project>/logs/ for post-mortem analysis.

set -euo pipefail

HARNESS_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$HARNESS_DIR/../.." && pwd)"

# Defaults
SPEC_FILE="$HARNESS_DIR/sample_spec.md"
LANGUAGE="node"
PROJECT_NAME="test-run"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --spec-file)
            SPEC_FILE="$2"
            shift 2
            ;;
        --language)
            LANGUAGE="$2"
            shift 2
            ;;
        --name)
            PROJECT_NAME="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--spec-file <path>] [--language node|python|dotnet] [--name <project>]"
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

# Create timestamped run directory
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="$HARNESS_DIR/runs/$TIMESTAMP"
mkdir -p "$RUN_DIR"

echo "============================================"
echo " Test Harness Run"
echo "============================================"
echo "  Run dir:    $RUN_DIR"
echo "  Spec file:  $SPEC_FILE"
echo "  Language:    $LANGUAGE"
echo "  Project:     $PROJECT_NAME"
echo "============================================"
echo ""

# Run from the timestamped directory
cd "$RUN_DIR"

agentic-dev go \
    --name "$PROJECT_NAME" \
    --spec-file "$SPEC_FILE" \
    --language "$LANGUAGE" \
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
echo "  Bare repo:  $RUN_DIR/$PROJECT_NAME/remote.git/"
echo "============================================"

exit $EXIT_CODE
