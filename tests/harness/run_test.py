from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_command(command: list[str], cwd: Path | None = None, quiet: bool = False) -> int:
    stdout = subprocess.DEVNULL if quiet else None
    stderr = subprocess.STDOUT if quiet else None
    process = subprocess.run(command, cwd=str(cwd) if cwd else None, stdout=stdout, stderr=stderr)
    return process.returncode


def ensure_python() -> str:
    venv_python = Path(__file__).resolve().parents[2] / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def ensure_agentic_dev(project_root: Path) -> str | None:
    venv_agent = project_root / ".venv" / "Scripts" / "agentic-dev.exe"
    if venv_agent.exists():
        return str(venv_agent)
    return shutil.which("agentic-dev")


def run_preflight(project_root: Path, python_exe: str) -> bool:
    print("============================================")
    print(" Pre-flight setup")
    print("============================================")

    build_dir = project_root / "build"
    if build_dir.exists():
        print("  Removing stale build/ directory...")
        shutil.rmtree(build_dir)

    print("  Installing package (pip install -e .)...")
    if run_command([python_exe, "-m", "pip", "install", "-e", str(project_root)], quiet=False) != 0:
        return False

    if not ensure_agentic_dev(project_root):
        print("ERROR: agentic-dev not found on PATH after install.")
        print(f"Try: {python_exe} -m pip install -e {project_root}")
        return False
    print("  ✓ agentic-dev is available")

    print("  Running unit tests...")
    if run_command([python_exe, "-m", "pytest", str(project_root / "tests"), "-q"], quiet=False) != 0:
        print("")
        print("ERROR: Unit tests failed. Fix them before running the harness.")
        return False
    print("")
    return True


def find_resume_target(runs_dir: Path, project_name: str) -> Path | None:
    if not runs_dir.exists():
        return None
    candidates: list[Path] = []
    for ts_dir in sorted(runs_dir.iterdir(), reverse=True):
        if not ts_dir.is_dir():
            continue
        project_dir = ts_dir / project_name
        if (project_dir / "remote.git").is_dir():
            candidates.append(project_dir)
    if not candidates:
        return None
    return candidates[0]


def confirm(prompt: str) -> bool:
    answer = input(prompt).strip().lower()
    return answer in ("", "y", "yes")


def run_harness() -> int:
    script_path = Path(__file__).resolve()
    harness_dir = script_path.parent
    project_root = harness_dir.parent.parent

    parser = argparse.ArgumentParser(description="Run local test harness")
    parser.add_argument("--spec-file", default=None)
    parser.add_argument("--name", default="test-run")
    parser.add_argument("--model", required=True, help="Copilot model to use (e.g. gpt-5.3-codex, claude-opus-4.6)")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--builders", type=int, default=1, help="Number of parallel builders (default 1)")
    args = parser.parse_args()

    python_exe = ensure_python()
    if not run_preflight(project_root, python_exe):
        return 1

    agentic_dev = ensure_agentic_dev(project_root)
    if not agentic_dev:
        print("ERROR: agentic-dev not found.")
        return 1

    runs_dir = harness_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    if args.resume:
        spec_file_for_resume: Path | None = None
        if args.spec_file:
            candidate = Path(args.spec_file).resolve()
            if candidate.exists():
                spec_file_for_resume = candidate

        project_dir = find_resume_target(runs_dir, args.name)
        if not project_dir:
            print(f"ERROR: No existing run found for project '{args.name}'.")
            return 1

        print("============================================")
        print(" Resuming existing run")
        print("============================================")
        print(f"  Directory:  {project_dir}")
        print(f"  Project:    {args.name}")
        if spec_file_for_resume:
            print(f"  New spec:   {spec_file_for_resume}")
        print("============================================")
        print("")

        if not confirm("Proceed? [Y/n] "):
            print("Aborted.")
            return 0

        for agent_dir in ("builder", "reviewer", "tester", "validator"):
            path = project_dir / agent_dir
            if path.exists():
                print(f"  Removing {agent_dir}/...")
                shutil.rmtree(path)
        # Also remove numbered builder directories (builder-1, builder-2, ...)
        for builder_path in sorted(project_dir.glob("builder-*")):
            if builder_path.is_dir():
                print(f"  Removing {builder_path.name}/...")
                shutil.rmtree(builder_path)

        command = [agentic_dev, "go", "--directory", str(project_dir), "--model", args.model, "--local",
                   "--builders", str(args.builders)]
        if spec_file_for_resume:
            command.extend(["--spec-file", str(spec_file_for_resume)])
        exit_code = run_command(command)
    else:
        spec_arg = args.spec_file or str(harness_dir / "sample_spec_cli_calculator.md")
        spec_file = Path(spec_arg).resolve()
        if not spec_file.exists():
            print(f"ERROR: Spec file not found: {spec_file}")
            return 1

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = runs_dir / timestamp
        project_dir = run_dir / args.name

        print("============================================")
        print(" Test Harness Run")
        print("============================================")
        print(f"  Run dir:    {run_dir}")
        print(f"  Spec file:  {spec_file}")
        print(f"  Project:    {args.name}")
        print("============================================")
        print("")

        if not confirm("Proceed? [Y/n] "):
            print("Aborted.")
            return 0

        run_dir.mkdir(parents=True, exist_ok=True)
        exit_code = run_command(
            [
                agentic_dev,
                "go",
                "--directory",
                str(project_dir),
                "--model",
                args.model,
                "--spec-file",
                str(spec_file),
                "--builders",
                str(args.builders),
                "--local",
            ]
        )

    print("")
    print("============================================")
    print(f" Run complete (exit code: {exit_code})")
    print("============================================")
    print(f"  Logs:       {project_dir / 'logs'}")
    print(f"  Builder:    {project_dir / 'builder'}")
    print(f"  Reviewer:   {project_dir / 'reviewer'}")
    print(f"  Tester:     {project_dir / 'tester'}")
    print(f"  Validator:  {project_dir / 'validator'}")
    if (project_dir / "remote.git").is_dir():
        print(f"  Bare repo:  {project_dir / 'remote.git'}")
    print("============================================")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(run_harness())
