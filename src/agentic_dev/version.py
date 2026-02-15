"""Version information with git commit tracking.

Reports the package version plus the commit date and hash, so you can
always tell exactly what code is running — even with editable installs.
All git commands run against this file's repo, not the caller's cwd.
"""

import os
import subprocess

PACKAGE_VERSION = "1.0.0"

_REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_git(*args: str) -> str | None:
    """Run a git command in the source repo directory. Return stdout or None on failure."""
    try:
        result = subprocess.run(
            ["git", "-C", _REPO_DIR, *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def get_version() -> str:
    """Return version string like '1.0.0 build 59 (2026-02-13 g3a7f2c1)'."""
    commit = _run_git("rev-parse", "--short", "HEAD") or "unknown"
    date = _run_git("log", "-1", "--format=%cs") or "unknown"
    build = _run_git("rev-list", "--count", "HEAD") or "0"
    dirty = "+dirty" if (_run_git("status", "--porcelain") or "") != "" else ""
    return f"{PACKAGE_VERSION} build {build} ({date} g{commit}{dirty})"
