"""Signal parsing for breaker agent output."""

_TOKEN_CLEAR = "ETCH_ALL_CLEAR"
_TOKEN_ISSUES = "ETCH_ISSUES_FOUND"
_PUNCTUATION_ONLY = set("-=*_`~><|")


def parse(output: str) -> str:
    """Parse breaker agent output for control tokens.

    Returns the signal corresponding to whichever token appears first.
    If both appear, the earlier one wins. If neither appears, returns
    "issues" as a fail-safe.

    Returns:
        "clear"  — ETCH_ALL_CLEAR found (and appears before ETCH_ISSUES_FOUND)
        "issues" — ETCH_ISSUES_FOUND found, appears first, or neither found
    """
    if not isinstance(output, str):
        return "issues"

    clear_pos = output.find(_TOKEN_CLEAR)
    issues_pos = output.find(_TOKEN_ISSUES)

    if clear_pos == -1 and issues_pos == -1:
        # Fail-safe: no token found → assume issues
        return "issues"

    if clear_pos == -1:
        return "issues"

    if issues_pos == -1:
        return "clear"

    # Both found — whichever appears first wins
    if clear_pos < issues_pos:
        return "clear"
    return "issues"


def extract_commit_message(output: str, fallback: str) -> str:
    """Extract a short commit message from fixer output.

    Looks for the first substantive line that describes what was changed.
    Falls back to `fallback` if nothing useful is found.
    Returns a string starting with 'fix(edge): '.
    """
    if not isinstance(output, str) or not output.strip():
        return fallback

    _SKIP_STARTS = ("i ", "i've ", "i have ", "here ", "the following", "done", "no ")
    _SKIP_WORDS = {"ok", "done", "nothing", "complete", "finished"}

    for line in output.splitlines():
        stripped = line.strip().lstrip("-*•").strip().strip("`").strip()
        if not stripped or len(stripped) < 8:
            continue
        if stripped.startswith("#"):
            continue
        if all(c in _PUNCTUATION_ONLY for c in stripped):
            continue
        lower = stripped.lower()
        if lower in _SKIP_WORDS:
            continue
        if any(lower.startswith(p) for p in _SKIP_STARTS):
            continue
        # Trim to a reasonable length and strip trailing punctuation
        msg = stripped[:72].rstrip(".,;:")
        if not msg:
            continue
        if not msg.lower().startswith("fix"):
            msg = f"fix(edge): {msg[0].lower()}{msg[1:]}"
        return msg

    return fallback


def extract_summary(output: str) -> str:
    """Extract the ETCH_SUMMARY line written by an agent.

    Agents are prompted to write a line like:
        ETCH_SUMMARY: fixed 3 null-guard issues in auth.py

    Returns the summary text, or empty string if not found.
    """
    if not isinstance(output, str):
        return ""
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("ETCH_SUMMARY:"):
            return stripped[len("ETCH_SUMMARY:"):].strip()
    return ""


def extract_finding(output: str) -> str:
    """Extract first meaningful line before the signal token.

    Returns the first non-empty, non-header line that appears before
    the signal token, or an empty string if nothing useful is found.
    """
    if not isinstance(output, str) or not output.strip():
        return ""

    # Find the position of either token
    clear_pos = output.find(_TOKEN_CLEAR)
    issues_pos = output.find(_TOKEN_ISSUES)

    # Determine the cutoff point (use whichever token appears first)
    cutoff = len(output)
    if clear_pos >= 0 and issues_pos >= 0:
        cutoff = min(clear_pos, issues_pos)
    elif clear_pos >= 0:
        cutoff = clear_pos
    elif issues_pos >= 0:
        cutoff = issues_pos

    text_before = output[:cutoff].strip()
    if not text_before:
        return ""

    lines = text_before.splitlines()
    for line in reversed(lines):
        stripped = line.strip().strip("`").strip()
        # Skip empty lines, markdown headers, separator lines, and bare punctuation
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if all(c in _PUNCTUATION_ONLY for c in stripped):
            continue
        return stripped

    return ""
