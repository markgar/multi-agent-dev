"""Platform-agnostic test harness for end-to-end orchestration runs.

Usage:
    python tests/harness/run_test.py --name stretto --model claude-opus-4.6 \\
        --spec-file tests/harness/sample_spec_stretto.md
    python tests/harness/run_test.py --name stretto --model claude-opus-4.6 --resume
    python tests/harness/run_test.py --name stretto --model claude-opus-4.6 \\
        --builders 4 --reviewer-model claude-sonnet-4.6

Handles all setup automatically:
  1. Cleans stale build/ artifacts
  2. Installs the package in editable mode (pip install -e .)
  3. Runs existing tests to catch problems early
  4. Creates a timestamped run directory under tests/harness/runs/
  5. Launches agentic-dev go
  6. Prints log locations for post-mortem analysis

Resume mode (--resume):
  Finds the latest existing run matching --name and resumes it via --directory.
  Deletes agent clone directories to simulate starting on a fresh machine.
  Optionally accepts a new --spec-file to add requirements.
"""

from __future__ import annotations

import argparse
import fnmatch
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_command(command: list[str], cwd: Path | None = None) -> int:
    """Run a command, inheriting stdin/stdout/stderr. Returns exit code."""
    process = subprocess.run(command, cwd=str(cwd) if cwd else None)
    return process.returncode


def ensure_python() -> str:
    """Find the best Python executable (prefer venv)."""
    project_root = Path(__file__).resolve().parents[2]
    for venv_python in (
        project_root / ".venv" / "Scripts" / "python.exe",  # Windows
        project_root / ".venv" / "bin" / "python",          # Unix
    ):
        if venv_python.exists():
            return str(venv_python)
    return sys.executable


def ensure_agentic_dev(project_root: Path) -> str | None:
    """Find the agentic-dev CLI executable."""
    for agent_path in (
        project_root / ".venv" / "Scripts" / "agentic-dev.exe",  # Windows
        project_root / ".venv" / "bin" / "agentic-dev",          # Unix
    ):
        if agent_path.exists():
            return str(agent_path)
    return shutil.which("agentic-dev")


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

def run_preflight(project_root: Path, python_exe: str) -> bool:
    """Clean, install, verify CLI, run tests. Returns True on success."""
    print("============================================")
    print(" Pre-flight setup")
    print("============================================")

    build_dir = project_root / "build"
    if build_dir.exists():
        print("  Removing stale build/ directory...")
        shutil.rmtree(build_dir)

    print("  Installing package (pip install -e .)...")
    rc = run_command([python_exe, "-m", "pip", "install", "-e", str(project_root), "--quiet"])
    if rc != 0:
        print("ERROR: pip install failed.")
        return False

    if not ensure_agentic_dev(project_root):
        print("ERROR: agentic-dev not found on PATH after install.")
        print(f"Try: {python_exe} -m pip install -e {project_root}")
        return False
    print("  ✓ agentic-dev is available")

    print("  Running unit tests...")
    rc = run_command([python_exe, "-m", "pytest", str(project_root / "tests"), "-q"])
    if rc != 0:
        print("")
        print("ERROR: Unit tests failed. Fix them before running the harness.")
        return False
    print("")
    return True


# ---------------------------------------------------------------------------
# Resume helpers
# ---------------------------------------------------------------------------

def find_resume_candidates(runs_dir: Path, project_name: str) -> list[Path]:
    """Find all run directories matching project_name (exact or name-* glob).

    Matches are detected by the presence of remote.git/ or builder-1/.
    Returns newest-first.
    """
    if not runs_dir.exists():
        return []
    candidates: list[Path] = []
    for ts_dir in sorted(runs_dir.iterdir(), reverse=True):
        if not ts_dir.is_dir():
            continue
        for child in sorted(ts_dir.iterdir()):
            if not child.is_dir():
                continue
            if child.name == project_name or fnmatch.fnmatch(child.name, f"{project_name}-*"):
                if (child / "remote.git").is_dir() or (child / "builder-1").is_dir():
                    candidates.append(child)
    return candidates


def pick_resume_target(candidates: list[Path], project_name: str, runs_dir: Path) -> Path | None:
    """Prompt the user to pick a resume target if multiple matches exist."""
    if not candidates:
        print(f"ERROR: No existing run found for project '{project_name}'.")
        print("")
        print(f"Available runs in {runs_dir}:")
        found_any = False
        if runs_dir.exists():
            for ts_dir in sorted(runs_dir.iterdir(), reverse=True):
                if not ts_dir.is_dir():
                    continue
                for child in sorted(ts_dir.iterdir()):
                    if child.is_dir() and ((child / "remote.git").is_dir() or (child / "builder-1").is_dir()):
                        print(f"  {child}")
                        found_any = True
        if not found_any:
            print("  (none found)")
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Multiple matches — let the user pick
    print("")
    print(f"Multiple runs found for '{project_name}':")
    print("")
    for i, candidate in enumerate(candidates):
        ts_name = candidate.parent.name
        marker = " (latest)" if i == 0 else ""
        print(f"  {i + 1}) {ts_name}/{candidate.name}{marker}")
    print("")
    try:
        pick = input("Which run? [1] ").strip() or "1"
        idx = int(pick) - 1
        if 0 <= idx < len(candidates):
            return candidates[idx]
    except (ValueError, EOFError):
        pass
    print("Invalid selection.")
    return None


def clean_agent_dirs(project_dir: Path) -> None:
    """Delete agent clone directories to simulate starting on a fresh machine."""
    for agent_name in ("builder", "reviewer", "milestone-reviewer", "tester", "validator"):
        path = project_dir / agent_name
        if path.exists():
            print(f"  Removing {agent_name}/...")
            shutil.rmtree(path)
    for pattern in ("builder-*", "reviewer-*"):
        for agent_path in sorted(project_dir.glob(pattern)):
            if agent_path.is_dir():
                print(f"  Removing {agent_path.name}/...")
                shutil.rmtree(agent_path)


# ---------------------------------------------------------------------------
# GO command assembly
# ---------------------------------------------------------------------------

def build_go_command(
    agentic_dev: str,
    project_dir: Path,
    model: str,
    builders: int,
    spec_file: Path | None = None,
    org: str | None = None,
    builder_model: str | None = None,
    reviewer_model: str | None = None,
    milestone_reviewer_model: str | None = None,
    tester_model: str | None = None,
    validator_model: str | None = None,
    planner_model: str | None = None,
) -> list[str]:
    """Assemble the agentic-dev go command with all flags."""
    command = [agentic_dev, "go", "--directory", str(project_dir), "--model", model, "--builders", str(builders)]
    if spec_file:
        command.extend(["--spec-file", str(spec_file)])
    if org:
        command.extend(["--org", org])
    if builder_model:
        command.extend(["--builder-model", builder_model])
    if reviewer_model:
        command.extend(["--reviewer-model", reviewer_model])
    if milestone_reviewer_model:
        command.extend(["--milestone-reviewer-model", milestone_reviewer_model])
    if tester_model:
        command.extend(["--tester-model", tester_model])
    if validator_model:
        command.extend(["--validator-model", validator_model])
    if planner_model:
        command.extend(["--planner-model", planner_model])
    return command


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Platform-agnostic test harness for end-to-end orchestration runs.",
    )
    parser.add_argument("--name", required=True, help="Project name (required)")
    parser.add_argument("--model", required=True, help="Copilot model (e.g. claude-opus-4.6)")
    parser.add_argument("--spec-file", default=None, help="Path to spec markdown file")
    parser.add_argument("--resume", action="store_true", help="Resume the latest run for --name")
    parser.add_argument("--builders", type=int, default=1, help="Number of parallel builders (default 1)")
    parser.add_argument("--org", default=None, help="GitHub org (default: personal account)")
    parser.add_argument("--builder-model", default=None, help="Model override for builders")
    parser.add_argument("--reviewer-model", default=None, help="Model override for commit-watcher reviewers")
    parser.add_argument("--milestone-reviewer-model", default=None, help="Model override for milestone reviewer")
    parser.add_argument("--tester-model", default=None, help="Model override for tester")
    parser.add_argument("--validator-model", default=None, help="Model override for validator")
    parser.add_argument("--planner-model", default=None, help="Model override for planner")
    return parser.parse_args()


def run_harness() -> int:
    args = parse_args()

    harness_dir = Path(__file__).resolve().parent
    project_root = harness_dir.parent.parent
    runs_dir = harness_dir / "runs"

    # Pre-flight
    python_exe = ensure_python()
    if not run_preflight(project_root, python_exe):
        return 1

    agentic_dev = ensure_agentic_dev(project_root)
    if not agentic_dev:
        print("ERROR: agentic-dev not found.")
        return 1

    # Agent model kwargs (shared between fresh and resume)
    model_kwargs = dict(
        builder_model=args.builder_model,
        reviewer_model=args.reviewer_model,
        milestone_reviewer_model=args.milestone_reviewer_model,
        tester_model=args.tester_model,
        validator_model=args.validator_model,
        planner_model=args.planner_model,
    )

    if args.resume:
        # --- Resume existing run ---
        spec_file: Path | None = None
        if args.spec_file:
            candidate = Path(args.spec_file).resolve()
            if candidate.exists():
                spec_file = candidate

        candidates = find_resume_candidates(runs_dir, args.name)
        project_dir = pick_resume_target(candidates, args.name, runs_dir)
        if not project_dir:
            return 1

        print("============================================")
        print(" Resuming existing run")
        print("============================================")
        print(f"  Directory:  {project_dir}")
        print(f"  Project:    {project_dir.name}")
        if spec_file:
            print(f"  New spec:   {spec_file}")
        print("============================================")
        print("")

        clean_agent_dirs(project_dir)
        print("")

        command = build_go_command(
            agentic_dev, project_dir, args.model, args.builders,
            spec_file=spec_file, org=args.org, **model_kwargs,
        )
        exit_code = run_command(command)
    else:
        # --- Fresh run ---
        spec_arg = args.spec_file or str(harness_dir / "sample_spec_cli_calculator.md")
        spec_file = Path(spec_arg).resolve()
        if not spec_file.exists():
            print(f"ERROR: Spec file not found: {spec_file}")
            return 1

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = runs_dir / timestamp
        project_dir = run_dir / f"{args.name}-{timestamp}"

        print("============================================")
        print(" Test Harness Run")
        print("============================================")
        print(f"  Run dir:    {run_dir}")
        print(f"  Spec file:  {spec_file}")
        print(f"  Project:    {args.name}-{timestamp}")
        print("============================================")
        print("")

        run_dir.mkdir(parents=True, exist_ok=True)

        command = build_go_command(
            agentic_dev, project_dir, args.model, args.builders,
            spec_file=spec_file, org=args.org, **model_kwargs,
        )
        exit_code = run_command(command)

    print("")
    print("============================================")
    print(f" Run complete (exit code: {exit_code})")
    print("============================================")
    print(f"  Logs:       {project_dir / 'logs'}")
    print(f"  Project:    {project_dir}")
    print(f"  Resume:     --resume --name {args.name}")
    print("============================================")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(run_harness())
