"""Codebase analysis for generating tailored prompt files."""

from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path


_LANG_MAP: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".cpp": "C++",
    ".c": "C",
    ".cs": "C#",
    ".php": "PHP",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".hs": "Haskell",
    ".scala": "Scala",
    ".clj": "Clojure",
    ".lua": "Lua",
    ".sh": "Shell",
    ".bash": "Shell",
}

_FRAMEWORK_HINTS: dict[str, str] = {
    "pyproject.toml": "Python project",
    "setup.py": "Python project",
    "package.json": "Node.js project",
    "go.mod": "Go module",
    "Cargo.toml": "Rust crate",
    "Gemfile": "Ruby project",
    "pom.xml": "Java/Maven project",
    "build.gradle": "Java/Gradle project",
    "mix.exs": "Elixir/Mix project",
    "composer.json": "PHP project",
}

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", "target", "vendor", ".cache",
}


def analyze(root: Path | None = None) -> dict:
    """Analyze a codebase and return structured info.

    Returns a dict with keys:
        languages: list of (language, file_count) sorted by count
        source_dirs: list of top-level source directories
        entry_points: list of likely entry point files
        framework: detected framework/project type string or None
        total_files: int
        is_git: bool
    """
    root = root or Path.cwd()

    files = _list_files(root)
    total = len(files)

    # Language detection
    ext_counts: Counter[str] = Counter()
    for f in files:
        ext = Path(f).suffix.lower()
        if ext in _LANG_MAP:
            ext_counts[ext] += 1

    lang_counts: Counter[str] = Counter()
    for ext, count in ext_counts.items():
        lang_counts[_LANG_MAP[ext]] += count

    languages = lang_counts.most_common(3)

    # Source directories (top-level dirs that contain source files)
    top_dirs: Counter[str] = Counter()
    for f in files:
        parts = Path(f).parts
        if len(parts) > 1 and parts[0] not in _SKIP_DIRS:
            top_dirs[parts[0]] += 1

    source_dirs = [d for d, _ in top_dirs.most_common(5) if not d.startswith(".")]

    # Entry points
    entry_points = _find_entry_points(root, files)

    # Framework detection
    framework = None
    for marker, label in _FRAMEWORK_HINTS.items():
        if (root / marker).exists():
            framework = label
            break

    return {
        "languages": languages,
        "source_dirs": source_dirs,
        "entry_points": entry_points,
        "framework": framework,
        "total_files": total,
        "is_git": (root / ".git").exists(),
        "root": root,
    }


def build_init_prompt(info: dict) -> str:
    """Build the Claude prompt used during etch init to analyze the codebase."""
    root = info.get("root", Path.cwd())
    file_tree = "\n".join(f"  {f}" for f in _list_files(root)[:60])
    if not file_tree:
        file_tree = "  (no tracked files)"

    lang_summary = ", ".join(f"{lang} ({n})" for lang, n in info["languages"]) or "unknown"
    framework = info["framework"] or "unknown"

    return f"""You are analyzing a codebase to configure an automated edge-case hunting tool.

The tool will run Claude Code in a fix-break loop to find and patch edge cases.
Your job is to write a focused scope description that tells the fixer exactly where to look.

## Codebase stats
- Framework: {framework}
- Languages: {lang_summary}
- Total files: {info["total_files"]}

## File tree
{file_tree}

## Instructions

Read the key source files in this codebase. Then write a concise scope description covering:
- The highest-risk areas for edge cases in THIS specific codebase
- Specific files or modules worth focusing on
- Any patterns you spotted that suggest missing error handling

Rules:
- Output ONLY the scope description as plain prose or bullet points
- No markdown headers, no preamble, no "here is the scope" intro
- Be specific to this codebase — not generic advice
- Keep it under 150 words
"""


def build_scan_md(info: dict, agent_scope: str | None = None) -> str:
    """Generate a tailored SCAN.md from analysis results."""
    scope = agent_scope.strip() if agent_scope else _format_scope(info)

    return f"""# SCAN — scanner prompt

You are a code analyst. Your job is to find genuine bugs before the fixer runs.

## Your mission

Read the codebase and produce a precise, actionable list of real issues:
- Unhandled edge cases and boundary conditions
- Missing null/None/empty checks that will cause crashes or wrong results
- Unhandled exceptions and error paths
- Off-by-one errors
- Race conditions or unsafe concurrent access
- Missing input validation at system boundaries

For each issue, include the file path, line number (if known), and a one-line description of what will go wrong.

## Rules

1. DO NOT edit any files — read only
2. Only report issues you are confident are genuine bugs — not observations, not style, not "could be cleaner"
3. If something is already handled correctly, do NOT report it — even if the handling is unusual
4. If you are unsure whether something is a bug, leave it out
5. List each confirmed issue on its own line, e.g.:
   - src/auth.py:42 — crashes with empty token string (no guard)
   - src/api.js:108 — unhandled promise rejection will silently fail
6. End your output with EXACTLY one of these tokens on its own line:
   - `ETCH_ISSUES_FOUND` — if you found confirmed bugs worth fixing
   - `ETCH_ALL_CLEAR` — if the code looks solid or you found nothing certain

## Scope

{scope}
"""


def build_etch_md(info: dict, agent_scope: str | None = None) -> str:
    """Generate a tailored ETCH.md from analysis results."""
    scope = agent_scope.strip() if agent_scope else _format_scope(info)

    return f"""# ETCH — fixer prompt

You are a surgical code reviewer focused on edge cases and robustness.

## Your mission

Scan the codebase for:
- Unhandled edge cases and boundary conditions
- Missing null/None/empty checks
- Unhandled exceptions and error paths
- Off-by-one errors
- Race conditions or unsafe concurrent access
- Missing input validation at system boundaries

## Rules

1. Fix only what you find — do not refactor, rename, or reorganize
2. One logical fix per commit (the harness will commit for you)
3. Do not add comments explaining what you fixed
4. If you find nothing, make no changes

## Scope

{scope}

## Commit format

The harness commits automatically. Each commit will be:
  fix(edge): <short description of what was fixed>
"""


def build_break_md(info: dict, agent_scope: str | None = None) -> str:
    """Generate a tailored BREAK.md from analysis results."""
    scope = agent_scope.strip() if agent_scope else _format_scope(info)

    return f"""# BREAK — breaker prompt

You are an adversarial code reviewer. Your job is to find anything that could go wrong.

## Your mission

Scan the entire codebase with fresh eyes. Do not limit yourself to recent changes.

Look for:
- Edge cases and boundary conditions that are unhandled anywhere in the code
- Functions that assume valid input without checking
- Error paths that are silently swallowed or ignored
- Race conditions, off-by-one errors, null/empty/zero not guarded
- Anything that would cause unexpected behavior in production

Be adversarial — think like someone actively trying to make this code fail.

## Rules

1. DO NOT edit any files — read only
2. Report your findings clearly, one per line
3. End your output with EXACTLY one of these tokens on its own line:
   - `ETCH_ISSUES_FOUND` — if you found anything worth fixing
   - `ETCH_ALL_CLEAR` — if the code looks solid

## Scope

{scope}
"""


def _format_scope(info: dict) -> str:
    lines = []
    if info["source_dirs"]:
        dirs = "  ".join(f"{d}/" for d in info["source_dirs"])
        lines.append(f"Directories: {dirs}")
    if info["entry_points"]:
        eps = "  ".join(info["entry_points"][:3])
        lines.append(f"Entry points: {eps}")
    if info["framework"]:
        lines.append(f"Project type: {info['framework']}")
    lines.append(f"Total tracked files: {info['total_files']}")
    return "\n".join(lines) if lines else "Entire repository"


def _list_files(root: Path) -> list[str]:
    """Return tracked files via git ls-files, falling back to filesystem walk."""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: walk filesystem
    files = []
    try:
        for p in root.rglob("*"):
            if p.is_file() and not any(part in _SKIP_DIRS for part in p.parts):
                try:
                    files.append(str(p.relative_to(root)))
                except ValueError:
                    pass
    except OSError:
        pass
    return files


def _find_entry_points(root: Path, files: list[str]) -> list[str]:
    """Heuristically identify entry point files."""
    candidates = []
    names = {"main.py", "app.py", "index.ts", "index.js", "main.go",
              "main.rs", "server.py", "server.ts", "cli.py", "manage.py"}
    for f in files:
        if Path(f).name in names:
            candidates.append(f)
    return candidates[:4]
