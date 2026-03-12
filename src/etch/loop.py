"""Core fix-break loop logic."""

from __future__ import annotations

import time
from pathlib import Path

from etch import agent, display, git, prompt, report, signals
from etch.agent import AgentError
from etch.git import GitError
from etch.prompt import PromptError, load_scan


_USER_PERSPECTIVE = """
## User perspective (additional lens)

Also think about this code from the perspective of a real end user interacting with it.
What inputs, sequences, or behaviors would a realistic user trigger that the code doesn't handle?

Look for:
- Empty, whitespace-only, or missing inputs where the code assumes content
- Inputs at the edges of what the interface allows (very long strings, zero, negative numbers)
- Unexpected but valid orderings of operations (calling things out of sequence)
- Malformed or non-UTF-8 data coming from files, network, or user input
- Concurrent use (two users/processes doing the same thing simultaneously)
- Users who skip optional steps, then trigger code that assumed they ran
- Realistic typos or near-valid inputs that bypass validation

Report only cases where the code would actually fail or behave incorrectly — not hypothetical misuse.
"""


def run(
    prompt_path: str | Path,
    max_iterations: int = 20,
    no_commit: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
    focus: str | None = None,
    user: bool = False,
) -> None:
    """Run the scan-fix-break loop."""
    prompt_path = Path(prompt_path)

    # ── Load prompts ──────────────────────────────────────────────────────────
    try:
        prompt_text = prompt.load(prompt_path)
    except PromptError as exc:
        display.print_error(str(exc))
        return

    if focus:
        prompt_text += f"\n\n## User focus\n\nConcentrate specifically on: {focus}\n"

    if dry_run:
        display.print_dry_run(prompt_text)
        return

    try:
        scan_text = prompt.load_scan(prompt_path)
    except PromptError as exc:
        display.print_error(str(exc))
        return

    try:
        break_text = prompt.load_break(prompt_path)
    except PromptError as exc:
        display.print_error(str(exc))
        return

    # Runner is optional — None means the phase is skipped
    try:
        run_text = prompt.load_run(prompt_path)
    except PromptError as exc:
        display.print_error(str(exc))
        return

    if focus:
        scan_text += f"\n\n## User focus\n\nConcentrate on: {focus}\n"
        break_text += f"\n\n## User focus\n\nConcentrate your adversarial review on: {focus}\n"

    if user:
        scan_text += _USER_PERSPECTIVE
        break_text += _USER_PERSPECTIVE

    start_time = time.monotonic()
    stats: dict = {
        "iterations": 0,
        "fixes": 0,
        "issues": 0,
        "reason": "done",
        "elapsed": 0.0,
    }
    last_breaker_signal: str | None = None
    last_breaker_output: str | None = None
    iteration_log: list[dict] = []
    final_runner_entry: dict = {}

    with display.EtchDisplay(target=str(prompt_path.parent)) as disp:

        # ── Main loop ─────────────────────────────────────────────────────────
        for iteration in range(1, max_iterations + 1):
            stats["iterations"] = iteration
            disp.start_iteration(iteration)
            iter_entry: dict = {"n": iteration}

            # ── Scanner phase ─────────────────────────────────────────────────
            disp.start_phase("scanner")
            scanner_start = time.monotonic()
            # Give the scanner any unresolved breaker findings as extra hints,
            # so it can verify whether those areas are still broken.
            effective_scan_text = scan_text
            if last_breaker_output:
                effective_scan_text += (
                    f"\n\n## Unresolved areas from previous adversarial review\n\n"
                    f"{last_breaker_output.strip()}\n\n"
                    f"Pay special attention to these spots — confirm whether each is "
                    f"still a genuine bug or has already been fixed.\n"
                )
            try:
                scanner_output = agent.run(effective_scan_text, verbose=verbose)
            except AgentError as exc:
                disp.finish_phase("scanner", status="error", detail=str(exc),
                                  duration=time.monotonic() - scanner_start, success=False)
                stats["reason"] = "agent_error"
                iteration_log.append(iter_entry)
                break

            scanner_duration = time.monotonic() - scanner_start
            scanner_signal = signals.parse(scanner_output)
            scanner_detail = (
                signals.extract_summary(scanner_output)
                or signals.extract_finding(scanner_output)
            )

            if scanner_signal == "clear":
                disp.finish_phase("scanner", status="all clear",
                                  detail=scanner_detail or "nothing to fix",
                                  duration=scanner_duration, success=True)
                iter_entry["scanner"] = {"status": "all clear", "detail": scanner_detail}
                stats["reason"] = "no_changes"
                iteration_log.append(iter_entry)
                break

            if scanner_signal == "empty":
                disp.finish_phase("scanner", status="no signal",
                                  detail="agent produced no output token",
                                  duration=scanner_duration, success=False)
                iter_entry["scanner"] = {"status": "no signal", "detail": "agent produced no output token"}
                stats["reason"] = "agent_error"
                iteration_log.append(iter_entry)
                break

            disp.finish_phase("scanner", status="issues found",
                              detail=scanner_detail or "issues found",
                              duration=scanner_duration, success=False)
            iter_entry["scanner"] = {"status": "issues found", "detail": scanner_detail}

            # ── Build fixer prompt ────────────────────────────────────────────
            # Only the scanner's confirmed findings go to the fixer — the scanner
            # already re-checked any breaker issues and reported only real ones.
            fixer_prompt = prompt_text
            fixer_prompt += (
                f"\n\n## Scanner findings\n\n{scanner_output.strip()}\n\n"
                f"Fix these specific issues.\n"
            )

            # ── Fixer phase ───────────────────────────────────────────────────
            disp.start_phase("fixer")
            fixer_start = time.monotonic()
            try:
                _fixer_output = agent.run(fixer_prompt, verbose=verbose)
            except AgentError as exc:
                disp.finish_phase("fixer", status="error", detail=str(exc),
                                  duration=time.monotonic() - fixer_start, success=False)
                stats["reason"] = "agent_error"
                iteration_log.append(iter_entry)
                break

            fixer_duration = time.monotonic() - fixer_start

            # ── Check for changes ─────────────────────────────────────────────
            try:
                changed = git.has_changes()
            except GitError as exc:
                disp.finish_phase("fixer", status="error", detail=str(exc),
                                  duration=fixer_duration, success=False)
                stats["reason"] = "git_error"
                iteration_log.append(iter_entry)
                break

            if not changed:
                disp.finish_phase("fixer", status="no changes", detail="nothing to fix",
                                  duration=fixer_duration, success=True)
                iter_entry["fixer"] = {"status": "no changes", "detail": "nothing to fix"}
                stats["reason"] = "stalled" if last_breaker_signal == "issues" else "no_changes"
                iteration_log.append(iter_entry)
                break

            # ── Commit ────────────────────────────────────────────────────────
            fixer_summary = (
                signals.extract_summary(_fixer_output)
                or signals.extract_commit_message(_fixer_output, fallback="")
            )
            commit_msg = signals.extract_commit_message(
                _fixer_output, fallback=f"fix(edge): iteration {iteration}"
            )
            if not no_commit:
                try:
                    git.commit(commit_msg)
                except GitError as exc:
                    disp.finish_phase("fixer", status="commit error", detail=str(exc),
                                      duration=fixer_duration, success=False)
                    stats["reason"] = "git_error"
                    iteration_log.append(iter_entry)
                    break

            disp.record_fix()
            stats["fixes"] += 1
            status_label = "changed" if no_commit else "committed"
            fixer_detail = fixer_summary or commit_msg
            disp.finish_phase("fixer", status=status_label, detail=fixer_detail,
                              duration=fixer_duration, success=True)
            iter_entry["fixer"] = {"status": status_label, "detail": fixer_detail}

            # ── Breaker phase ─────────────────────────────────────────────────
            disp.start_phase("breaker")
            breaker_start = time.monotonic()
            # Focus the breaker only on files the fixer actually changed.
            # This prevents the breaker from finding brand-new issues in
            # untouched files, which causes the loop to thrash.
            effective_break_text = break_text
            recent_files = git.changed_files(since_commits=1)
            if recent_files:
                files_list = "\n".join(f"- {f}" for f in recent_files)
                effective_break_text = break_text + (
                    f"\n\n## Scope for this iteration\n\n"
                    f"The fixer just changed these files — review ONLY these:\n"
                    f"{files_list}\n\n"
                    f"Do not scan files that were not changed.\n"
                )
            try:
                breaker_output = agent.run(effective_break_text, verbose=verbose)
            except AgentError as exc:
                disp.finish_phase("breaker", status="error", detail=str(exc),
                                  duration=time.monotonic() - breaker_start, success=False)
                stats["reason"] = "agent_error"
                iteration_log.append(iter_entry)
                break

            breaker_duration = time.monotonic() - breaker_start
            signal = signals.parse(breaker_output)
            last_breaker_signal = signal
            last_breaker_output = breaker_output if signal == "issues" else None
            breaker_detail = (
                signals.extract_summary(breaker_output)
                or signals.extract_finding(breaker_output)
            )

            if signal == "clear":
                disp.finish_phase("breaker", status="all clear",
                                  detail=breaker_detail or "no issues found",
                                  duration=breaker_duration, success=True)
                iter_entry["breaker"] = {"status": "all clear", "detail": breaker_detail}
                stats["reason"] = "clear"
                iteration_log.append(iter_entry)
                break
            elif signal == "empty":
                disp.finish_phase("breaker", status="no signal",
                                  detail="agent produced no output token",
                                  duration=breaker_duration, success=False)
                iter_entry["breaker"] = {"status": "no signal", "detail": "agent produced no output token"}
                stats["reason"] = "agent_error"
                iteration_log.append(iter_entry)
                break
            else:
                disp.record_issue()
                stats["issues"] += 1
                disp.finish_phase("breaker", status="issues",
                                  detail=breaker_detail or "issues found",
                                  duration=breaker_duration, success=False)
                iter_entry["breaker"] = {"status": "issues", "detail": breaker_detail}
                stats["reason"] = "issues"
                iteration_log.append(iter_entry)

        else:
            stats["reason"] = "max_iterations"

        # ── Runner — final step, only when loop ended cleanly ─────────────────
        if run_text and stats["reason"] == "clear":
            disp.start_phase("runner")
            runner_start = time.monotonic()
            try:
                runner_output = agent.run(run_text, verbose=verbose, timeout=600)
                runner_duration = time.monotonic() - runner_start
                runner_signal = signals.parse(runner_output)
                runner_detail = (
                    signals.extract_summary(runner_output)
                    or signals.extract_finding(runner_output)
                )
                if runner_signal == "clear":
                    disp.finish_phase("runner", status="all clear",
                                      detail=runner_detail or "build passed",
                                      duration=runner_duration, success=True)
                    final_runner_entry = {"status": "all clear", "detail": runner_detail}
                else:
                    disp.record_issue()
                    stats["issues"] += 1
                    disp.finish_phase("runner", status="build failed",
                                      detail=runner_detail or "build failed",
                                      duration=runner_duration, success=False)
                    final_runner_entry = {"status": "build failed", "detail": runner_detail}
                    stats["reason"] = "build_failed"
            except AgentError as exc:
                disp.finish_phase("runner", status="error",
                                  detail=str(exc),
                                  duration=time.monotonic() - runner_start, success=False)
                final_runner_entry = {"status": "error", "detail": str(exc)}
                stats["reason"] = "agent_error"

        stats["elapsed"] = time.monotonic() - start_time

    # Live panel is fully closed before printing anything below
    display.print_summary(stats)

    # ── Write report ──────────────────────────────────────────────────────────
    try:
        if final_runner_entry:
            iteration_log.append({"n": "runner", "runner": final_runner_entry})
        report_path = report.write(stats, iteration_log, output_dir=prompt_path.parent)
        if not no_commit and stats["fixes"] > 0:
            try:
                git.commit(f"etch: add run report {report_path.name}", paths=[str(report_path)])
            except GitError:
                pass  # report write is best-effort
        display.print_report_saved(report_path)
    except Exception:
        pass  # report is best-effort, never fail the run over it
