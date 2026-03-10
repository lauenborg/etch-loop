"""Git subprocess utilities."""

import subprocess


class GitError(Exception):
    """Raised when a git operation fails."""


def has_changes() -> bool:
    """Check whether the working tree has uncommitted changes.

    Runs `git diff --quiet HEAD` and interprets the exit code:
      0  — no changes
      1  — changes present
      other — git error

    Returns:
        True if there are uncommitted changes, False otherwise.

    Raises:
        GitError: If git is not available or returns an unexpected error.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--quiet", "HEAD"],
            capture_output=True,
        )
    except FileNotFoundError:
        raise GitError("git executable not found. Is git installed?")
    except OSError as exc:
        raise GitError(f"Failed to run git: {exc}") from exc

    if result.returncode == 1:
        return True

    # Exit code 0 means no tracked changes, but untracked files won't appear in
    # `git diff HEAD`.  Exit code 128 means no commits yet.  In both cases fall
    # through to `git status --porcelain` which covers all working-tree changes.
    if result.returncode not in (0, 128):
        raise GitError(f"git diff exited with unexpected code {result.returncode}")

    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise GitError(f"Failed to run git status: {exc}") from exc

    if status.returncode != 0:
        stderr = status.stderr.strip()
        raise GitError(f"git status failed (exit {status.returncode}): {stderr}")

    return bool(status.stdout.strip())


def changed_files(since_commits: int = 1) -> list[str]:
    """Return files changed in the last N commits.

    Used to focus the breaker on files the fixer actually touched,
    rather than the entire codebase.

    Returns an empty list if git is unavailable or no commits exist.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"HEAD~{since_commits}", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()
    except (OSError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return []


def commit(message: str, paths: list[str] | None = None) -> None:
    """Stage all changes and create a commit.

    Args:
        message: The commit message.

    Raises:
        GitError: If staging or committing fails.
    """
    if not message or not message.strip():
        raise GitError("Commit message must not be empty.")

    # Stage all changes (or specific paths)
    add_cmd = ["git", "add"] + (paths if paths else ["--all"])
    try:
        add_result = subprocess.run(
            add_cmd,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise GitError("git executable not found. Is git installed?")
    except OSError as exc:
        raise GitError(f"Failed to run git add: {exc}") from exc

    if add_result.returncode != 0:
        stderr = add_result.stderr.strip()
        raise GitError(f"git add -A failed (exit {add_result.returncode}): {stderr}")

    # Create commit
    try:
        commit_result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise GitError(f"Failed to run git commit: {exc}") from exc

    if commit_result.returncode != 0:
        stderr = commit_result.stderr.strip()
        stdout = commit_result.stdout.strip()
        detail = stderr or stdout
        raise GitError(
            f"git commit failed (exit {commit_result.returncode}): {detail}"
        )
