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

    if result.returncode == 0:
        return False
    if result.returncode == 1:
        return True

    # Non-zero, non-one exit code — could mean no commits yet, check with status
    # Fallback: check via git status --porcelain
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise GitError(f"Failed to run git status: {exc}") from exc

    if status.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise GitError(f"git diff failed (exit {result.returncode}): {stderr}")

    return bool(status.stdout.strip())


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
    add_cmd = ["git", "add"] + (paths if paths else ["-A"])
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
