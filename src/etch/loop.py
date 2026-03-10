"""Core fix-break loop logic."""

from __future__ import annotations

import time
from pathlib import Path

from etch import agent, display, git, prompt, signals
from etch.agent import AgentError
from etch.git import GitError
from etch.prompt import PromptError


def run(
    prompt_path: str | Path,
    max_iterations: int = 20,
    no_commit: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
    focus: str | None = None,
) -> None:
    """Run the fix-break loop.

    Args:
        prompt_path:    Path to ETCH.md (fixer prompt).
        max_iterations: Maximum number of fix-break cycles to run.
        no_commit:      If True, skip git commits after fixer runs.
        dry_run:        If True, print the prompt and exit without running.
        verbose:        If True, stream agent output to the terminal.
    """
    prompt_path = Path(prompt_path)

    # ── Load fixer prompt ──────────────────────────────────────────────────────
    try:
        prompt_text = prompt.load(prompt_path)
    except PromptError as exc:
        display.print_error(str(exc))
        return

    if focus:
        prompt_text += f"\n\n## User focus\n\nConcentrate specifically on: {focus}\n"

    # ── Dry run ───────────────────────────────────────────────────────────────
    if dry_run:
        display.print_dry_run(prompt_text)
        return

    # ── Load breaker prompt early to fail fast ────────────────────────────────
    try:
        break_text = prompt.load_break(prompt_path)
    except PromptError as exc:
        display.print_error(str(exc))
        return

    if focus:
        break_text += f"\n\n## User focus\n\nConcentrate your adversarial review on: {focus}\n"

    start_time = time.monotonic()
    stats: dict = {
        "iterations": 0,
        "fixes": 0,
        "issues": 0,
        "reason": "done",
        "elapsed": 0.0,
    }
    last_breaker_signal: str | None = None  # None = breaker hasn't run yet

    with display.EtchDisplay(target=str(prompt_path.parent)) as disp:
        for iteration in range(1, max_iterations + 1):
            stats["iterations"] = iteration
            disp.start_iteration(iteration)

            # ── Fixer phase ───────────────────────────────────────────────────
            disp.start_phase("fixer")
            fixer_start = time.monotonic()
            try:
                _fixer_output = agent.run(prompt_text, verbose=verbose)
            except AgentError as exc:
                disp.finish_phase(
                    "fixer",
                    status="error",
                    detail=str(exc),
                    duration=time.monotonic() - fixer_start,
                    success=False,
                )
                stats["reason"] = "agent_error"
                break

            fixer_duration = time.monotonic() - fixer_start

            # ── Check for changes ─────────────────────────────────────────────
            try:
                changed = git.has_changes()
            except GitError as exc:
                disp.finish_phase(
                    "fixer",
                    status="error",
                    detail=str(exc),
                    duration=fixer_duration,
                    success=False,
                )
                stats["reason"] = "git_error"
                break

            if not changed:
                disp.finish_phase(
                    "fixer",
                    status="no changes",
                    detail="nothing to fix",
                    duration=fixer_duration,
                    success=True,
                )
                # If the breaker has never run (first iteration with no diff),
                # stop immediately — nothing was ever changed, nothing to challenge.
                # If the breaker previously found issues, run it once more to
                # confirm whether those issues are still present or now resolved.
                if last_breaker_signal != "issues":
                    stats["reason"] = "no_changes"
                    break
                # Fall through to run the breaker one final time

            # ── Commit ────────────────────────────────────────────────────────
            commit_msg = f"fix(edge): iteration {iteration}"
            if not no_commit:
                try:
                    git.commit(commit_msg)
                except GitError as exc:
                    disp.finish_phase(
                        "fixer",
                        status="commit error",
                        detail=str(exc),
                        duration=fixer_duration,
                        success=False,
                    )
                    stats["reason"] = "git_error"
                    break

            disp.record_fix()
            stats["fixes"] += 1
            disp.finish_phase(
                "fixer",
                status="committed" if not no_commit else "changed",
                detail=commit_msg,
                duration=fixer_duration,
                success=True,
            )

            # ── Breaker phase ─────────────────────────────────────────────────
            disp.start_phase("breaker")
            breaker_start = time.monotonic()
            try:
                breaker_output = agent.run(break_text, verbose=verbose)
            except AgentError as exc:
                disp.finish_phase(
                    "breaker",
                    status="error",
                    detail=str(exc),
                    duration=time.monotonic() - breaker_start,
                    success=False,
                )
                stats["reason"] = "agent_error"
                break

            breaker_duration = time.monotonic() - breaker_start
            signal = signals.parse(breaker_output)
            last_breaker_signal = signal
            finding = signals.extract_finding(breaker_output)

            if signal == "clear":
                disp.finish_phase(
                    "breaker",
                    status="all clear",
                    detail=finding or "no issues found",
                    duration=breaker_duration,
                    success=True,
                )
                stats["reason"] = "clear"
                break
            else:
                disp.record_issue()
                stats["issues"] += 1
                disp.finish_phase(
                    "breaker",
                    status="issues",
                    detail=finding or "issues found",
                    duration=breaker_duration,
                    success=False,
                )
                stats["reason"] = "issues"
                # Continue to next iteration

        else:
            # Loop exhausted without break
            stats["reason"] = "max_iterations"

        stats["elapsed"] = time.monotonic() - start_time
        disp.print_summary(stats)
