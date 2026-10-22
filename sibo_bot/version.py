import os
import subprocess
from functools import cache

# Bumped automatically on every commit by .githooks/pre-commit.
APP_VERSION = "2.0.1"


@cache
def get_commit_sha() -> str:
    """Cloud Run injects COMMIT_SHA/K_REVISION; locally fall back to git."""
    commit = os.environ.get("COMMIT_SHA") or os.environ.get("K_REVISION")
    if commit:
        return commit
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
