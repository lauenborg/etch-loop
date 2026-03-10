"""Signal parsing for breaker agent output."""

import re

_TOKEN_CLEAR = "ETCH_ALL_CLEAR"
_TOKEN_ISSUES = "ETCH_ISSUES_FOUND"
_PUNCTUATION_ONLY = set("-=*_`~><|")


def parse(output: str) -> str:
    """Parse agent output for control tokens.

    Tokens must appear alone on their own line (after stripping whitespace
    and backtick wrappers). This prevents false matches when agents quote the
    token strings in explanations like `ETCH_ALL_CLEAR`.

    The first matching line wins. If neither token is found, returns "issues"
    as a fail-safe.

    Returns:
        "clear"  — ETCH_ALL_CLEAR found on its own line first
        "issues" — ETCH_ISSUES_FOUND found on its own line first, or no token found
        "empty"  — output is empty or whitespace-only (agent produced no content)
    """
    if not isinstance(output, str):
        return "issues"

    if not output.strip():
        return "empty"

    for line in output.splitlines():
        stripped = line.strip().strip("`").strip()
        if stripped == _TOKEN_CLEAR:
            return "clear"
        if stripped == _TOKEN_ISSUES:
            return "issues"

    return "issues"  # fail-safe: no token found


def extract_commit_message(output: str, fallback: str) -> str:
    """Extract a short commit message from fixer output.

    Tries ETCH_SUMMARY first (the explicit summary line), then falls back to
    scanning for the first substantive line that describes what was changed.
    Returns a string starting with 'fix(edge): '.
    """
    if not isinstance(output, str) or not output.strip():
        return fallback

    # Prefer the explicit ETCH_SUMMARY line
    summary = extract_summary(output)
    if summary:
        msg = summary[:72].rstrip(".,;: ")
        if not msg:
            return fallback
        if not msg.lower().startswith("fix"):
            msg = f"fix(edge): {msg[0].lower()}{msg[1:]}"
        return msg

    _SKIP_STARTS = ("i ", "i've ", "i have ", "here ", "here's", "the following", "done", "no ", "summary", "below")
    _SKIP_WORDS = {"ok", "done", "nothing", "complete", "finished"}

    for line in output.splitlines():
        stripped = line.strip().lstrip("-*•").strip().strip("`").strip()
        if not stripped or len(stripped) < 8:
            continue
        if _TOKEN_CLEAR in stripped or _TOKEN_ISSUES in stripped:
            break
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
        msg = stripped[:72].rstrip(".,;: ")
        if not msg or not any(c.isalnum() for c in msg):
            continue
        if not msg.lower().startswith("fix"):
            msg = f"fix(edge): {msg[0].lower()}{msg[1:]}"
        return msg

    return fallback


def extract_summary(output: str) -> str:
    """Extract the summary from an <etch_summary> tag in agent output.

    Agents are prompted to write:
        <etch_summary>fixed 3 null-guard issues in auth.py</etch_summary>

    Returns the summary text, or empty string if not found.
    """
    if not isinstance(output, str):
        return ""
    m = re.search(r"<etch_summary>(.*?)</etch_summary>", output, re.DOTALL)
    if m:
        return " ".join(m.group(1).split())
    return ""


def extract_finding(output: str) -> str:
    """Extract the last meaningful line before the signal token line.

    Scans line by line, stops at the first line that IS a token (exact match).
    Returns the last non-empty, non-header line before that point.
    """
    if not isinstance(output, str) or not output.strip():
        return ""

    lines_before: list[str] = []
    for line in output.splitlines():
        stripped = line.strip().strip("`").strip()
        if _TOKEN_CLEAR in stripped or _TOKEN_ISSUES in stripped:
            break
        lines_before.append(line)

    for line in reversed(lines_before):
        stripped = line.strip().strip("`").strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if all(c in _PUNCTUATION_ONLY for c in stripped):
            continue
        return stripped

    return ""
