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
