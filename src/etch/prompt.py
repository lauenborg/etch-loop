"""Prompt file loading utilities."""

from pathlib import Path


class PromptError(Exception):
    """Raised when a prompt file cannot be loaded or is invalid."""


def load(path: str | Path) -> str:
    """Load and return the content of a prompt file.

    Args:
        path: Path to the prompt file.

    Returns:
        File contents as a string.

    Raises:
        PromptError: If the file does not exist or is empty.
    """
    p = Path(path)
    if not p.exists():
        raise PromptError(f"Prompt file not found: {p}")
    if not p.is_file():
        raise PromptError(f"Prompt path is not a file: {p}")

    content = p.read_text(encoding="utf-8")
    if not content.strip():
        raise PromptError(f"Prompt file is empty: {p}")

    return content


def load_break(path: str | Path | None = None) -> str:
    """Load and return the content of BREAK.md.

    Searches in order:
    1. The explicit path if provided
    2. Same directory as the provided path (treating it as ETCH.md location)
    3. Current working directory

    Args:
        path: Optional path. If this is ETCH.md, looks for BREAK.md alongside it.
              If this is the BREAK.md path directly, loads it directly.

    Returns:
        File contents as a string.

    Raises:
        PromptError: If BREAK.md cannot be found or is empty.
    """
    candidates: list[Path] = []

    if path is not None:
        p = Path(path)
        # If caller passed BREAK.md directly
        if p.name.upper() == "BREAK.MD":
            candidates.append(p)
        else:
            # Treat path as ETCH.md — look for BREAK.md alongside it
            candidates.append(p.parent / "BREAK.md")

    # Always fall back to cwd
    candidates.append(Path.cwd() / "BREAK.md")

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            content = candidate.read_text(encoding="utf-8")
            if not content.strip():
                raise PromptError(f"BREAK.md is empty: {candidate}")
            return content

    searched = ", ".join(str(c) for c in candidates)
    raise PromptError(f"BREAK.md not found. Searched: {searched}")


def load_scan(path: str | Path | None = None) -> str:
    """Load and return the content of SCAN.md.

    Searches alongside ETCH.md first, then cwd.

    Raises:
        PromptError: If SCAN.md cannot be found or is empty.
    """
    candidates: list[Path] = []

    if path is not None:
        p = Path(path)
        if p.name.upper() == "SCAN.MD":
            candidates.append(p)
        else:
            candidates.append(p.parent / "SCAN.md")

    candidates.append(Path.cwd() / "SCAN.md")

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            content = candidate.read_text(encoding="utf-8")
            if not content.strip():
                raise PromptError(f"SCAN.md is empty: {candidate}")
            return content

    searched = ", ".join(str(c) for c in candidates)
    raise PromptError(f"SCAN.md not found. Searched: {searched}")
