"""`claudiscope update`: pull the latest version and refresh the install.

Two install types are handled:
  * a git checkout (pip install -e .): git pull --ff-only, then re-run pip install -e
  * a normal pip/pipx install from GitHub: pip install --upgrade from the repo URL
"""

import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/w1nston269/claudiscope"
RESTART_NOTE = (
    "Restart to load the new code: fully quit and reopen Claude Desktop (or start a new "
    "Claude Code session). A running server keeps using the old version until then."
)


def _run(cmd, cwd=None):
    """Run a command, returning CompletedProcess, or None if the program isn't installed."""
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        return None


def _project_root():
    """Return the repo root if we're running from a git checkout, else None."""
    root = Path(__file__).resolve().parents[2]
    if (root / "pyproject.toml").exists() and (root / ".git").exists():
        return root
    return None


def _installed_version():
    r = _run([sys.executable, "-c", "from importlib.metadata import version; print(version('claudiscope'))"])
    return r.stdout.strip() if r is not None and r.returncode == 0 else "unknown"


def _update_git(root, check_only=False, reinstall=True):
    def git(*args):
        return _run(["git", *args], cwd=root)

    r = git("fetch", "--quiet")
    if r is None:
        print("git isn't installed or isn't on your PATH.")
        return 1
    if r.returncode != 0:
        print("git fetch failed:\n" + r.stderr.strip())
        return 1

    r = git("rev-list", "--count", "HEAD..@{u}")
    if r.returncode != 0:
        print("This branch has no upstream to compare against. Try:\n"
              "  git branch --set-upstream-to=origin/main")
        return 1
    behind = int(r.stdout.strip())
    if behind == 0:
        print(f"Already up to date (claudiscope {_installed_version()}).")
        return 0

    print(f"{behind} new commit(s) available:")
    print(git("log", "--oneline", "HEAD..@{u}").stdout.strip())
    if check_only:
        print("\nRun `claudiscope update` to install them.")
        return 0

    if git("status", "--porcelain", "--untracked-files=no").stdout.strip():
        print("\nNote: you have uncommitted changes. Git will refuse the update if they conflict.")

    r = git("pull", "--ff-only", "--quiet")
    if r.returncode != 0:
        print("\ngit pull failed (local commits or edits that diverge from GitHub?):\n" + r.stderr.strip())
        print("Resolve it with git, then run the update again.")
        return 1

    if reinstall:
        print("Refreshing the install (picks up any new dependencies)...")
        r = _run([sys.executable, "-m", "pip", "install", "-e", str(root)])
        if r is None or r.returncode != 0:
            print("pip install failed:\n" + (r.stdout + r.stderr if r else "pip not found"))
            return 1

    head = git("rev-parse", "--short", "HEAD").stdout.strip()
    print(f"\nUpdated to commit {head}.\n{RESTART_NOTE}")
    return 0


def _update_pip(check_only=False):
    if check_only:
        print("--check only works for git checkouts. For a pip/pipx install, run `claudiscope update`.")
        return 0
    before = _installed_version()
    print(f"Installed: claudiscope {before}. Fetching the latest from {REPO_URL} ...")
    r = _run([sys.executable, "-m", "pip", "install", "--upgrade", "--force-reinstall",
              f"git+{REPO_URL}"])
    if r is None or r.returncode != 0:
        print("Update failed:\n" + (r.stdout + r.stderr if r else "pip not found"))
        print("If this is a pipx install, try: pipx upgrade claudiscope")
        return 1
    print(f"Now at claudiscope {_installed_version()} (was {before}).\n{RESTART_NOTE}")
    return 0


def run(check_only=False):
    root = _project_root()
    if root:
        print(f"Updating git checkout at {root}")
        return _update_git(root, check_only)
    return _update_pip(check_only)