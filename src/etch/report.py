"""Run report generation."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any


def write(
    stats: dict[str, Any],
    iterations: list[dict],
    output_dir: Path | None = None,
) -> Path:
    """Write a markdown report for a completed etch run.

    Args:
        stats:      Final stats dict from the loop.
        iterations: List of per-iteration dicts with scanner/fixer/breaker findings.
        output_dir: Directory to write the report. Defaults to cwd.

    Returns:
        Path to the written report file.
    """
    output_dir = output_dir or Path.cwd()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
    path = output_dir / f"etch-report-{timestamp}.md"

    lines: list[str] = []
    lines.append(f"# etch run — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    reason = stats.get("reason", "done")
    elapsed = _fmt_elapsed(stats.get("elapsed", 0.0))
    lines.append(f"**outcome:** {_reason_label(reason)}  ")
    lines.append(f"**iterations:** {stats.get('iterations', 0)}  ")
    lines.append(f"**fixes:** {stats.get('fixes', 0)}  ")
    lines.append(f"**breaker issues:** {stats.get('issues', 0)}  ")
    lines.append(f"**elapsed:** {elapsed}\n")

    for entry in iterations:
        n = entry.get("n", "?")
        lines.append(f"---\n\n## iteration {n}\n")

        scanner = entry.get("scanner")
        if scanner:
            status = scanner.get("status", "")
            detail = scanner.get("detail", "")
            lines.append(f"**scanner** — {status}")
            if detail:
                lines.append(f"\n> {detail}\n")

        fixer = entry.get("fixer")
        if fixer:
            status = fixer.get("status", "")
            detail = fixer.get("detail", "")
            lines.append(f"**fixer** — {status}")
            if detail:
                lines.append(f"\n> {detail}\n")

        breaker = entry.get("breaker")
        if breaker:
            status = breaker.get("status", "")
            detail = breaker.get("detail", "")
            lines.append(f"**breaker** — {status}")
            if detail:
                lines.append(f"\n> {detail}\n")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _reason_label(reason: str) -> str:
    return {
        "clear": "all clear",
        "no_changes": "clean — nothing to fix",
        "max_iterations": "stopped — max iterations reached",
        "interrupted": "interrupted",
        "agent_error": "stopped — agent error",
        "git_error": "stopped — git error",
    }.get(reason, reason)


def _fmt_elapsed(seconds: float) -> str:
    seconds = max(0.0, seconds)
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}m {secs}s" if mins else f"{secs}s"
