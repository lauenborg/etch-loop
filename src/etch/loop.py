"""Core fix-break loop logic."""

from __future__ import annotations

import time
from pathlib import Path

from etch import agent, display, git, prompt, report, signals
from etch.agent import AgentError
from etch.git import GitError
from etch.prompt import PromptError, load_scan


def run(
    prompt_path: str | Path,
    max_iterations: int = 20,
    no_commit: bool = False,
    no_git: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
    focus: str | None = None,
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
    run_text = prompt.load_run(prompt_path)

    if focus:
        scan_text += f"\n\n## User focus\n\nConcentrate on: {focus}\n"
        break_text += f"\n\n## User focus\n\nConcentrate your adversarial review on: {focus}\n"

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
    last_runner_output: str | None = None
    iteration_log: list[dict] = []

    with display.EtchDisplay(target=str(prompt_path.parent)) as disp:

        # ── Runner helper — called at every clean exit point ──────────────────
        def try_runner(iter_entry: dict) -> str:
            """Run the runner phase if configured.

            Returns:
                "skip"   — no RUN.md, proceed with clean exit
                "clear"  — runner passed, proceed with clean exit
                "issues" — runner failed, continue the loop
                "error"  — agent error, break the loop
            """
            nonlocal last_runner_output
            if not run_text:
                return "skip"

            disp.start_phase("runner")
            runner_start = time.monotonic()
            try:
                runner_output = agent.run(run_text, verbose=verbose)
            except AgentError as exc:
                disp.finish_phase("runner", status="error", detail=str(exc),
                                  duration=time.monotonic() - runner_start, success=False)
                return "error"

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
                iter_entry["runner"] = {"status": "all clear", "detail": runner_detail}
                last_runner_output = None
                return "clear"
            else:
                disp.record_issue()
                stats["issues"] += 1
                disp.finish_phase("runner", status="build failed",
                                  detail=runner_detail or "build failed",
                                  duration=runner_duration, success=False)
                iter_entry["runner"] = {"status": "build failed", "detail": runner_detail}
                last_runner_output = runner_output
                return "issues"

        # ── Main loop ─────────────────────────────────────────────────────────
        for iteration in range(1, max_iterations + 1):
            stats["iterations"] = iteration
            disp.start_iteration(iteration)
            iter_entry: dict = {"n": iteration}

            # ── Scanner phase ─────────────────────────────────────────────────
            disp.start_phase("scanner")
            scanner_start = time.monotonic()
            try:
                scanner_output = agent.run(scan_text, verbose=verbose)
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
                runner_result = try_runner(iter_entry)
                if runner_result == "error":
                    stats["reason"] = "agent_error"
                    iteration_log.append(iter_entry)
                    break
                elif runner_result == "issues":
                    stats["reason"] = "issues"
                    iteration_log.append(iter_entry)
                    continue
                else:  # "clear" or "skip"
                    stats["reason"] = "no_changes"
                    iteration_log.append(iter_entry)
                    break

            disp.finish_phase("scanner", status="issues found",
                              detail=scanner_detail or "issues found",
                              duration=scanner_duration, success=False)
            iter_entry["scanner"] = {"status": "issues found", "detail": scanner_detail}

            # ── Build fixer prompt ────────────────────────────────────────────
            fixer_prompt = prompt_text
            fixer_prompt += (
                f"\n\n## Scanner findings\n\n{scanner_output.strip()}\n\n"
                f"Fix these specific issues.\n"
            )
            if last_breaker_output:
                fixer_prompt += (
                    f"\n\n## Breaker findings from previous iteration\n\n"
                    f"{last_breaker_output.strip()}\n\n"
                    f"Also address these if not already covered above.\n"
                )
            if last_runner_output:
                fixer_prompt += (
                    f"\n\n## Build/test failures from previous iteration\n\n"
                    f"{last_runner_output.strip()}\n\n"
                    f"Fix the underlying code issues causing these failures.\n"
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

            # ── Check for changes (skipped when no_git) ───────────────────────
            if not no_git:
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
                    if last_breaker_signal != "issues":
                        runner_result = try_runner(iter_entry)
                        if runner_result == "error":
                            stats["reason"] = "agent_error"
                            iteration_log.append(iter_entry)
                            break
                        elif runner_result == "issues":
                            stats["reason"] = "issues"
                            iteration_log.append(iter_entry)
                            continue
                        else:  # "clear" or "skip"
                            stats["reason"] = "no_changes"
                            iteration_log.append(iter_entry)
                            break
                    iteration_log.append(iter_entry)
                    # Fall through to breaker

            # ── Commit ────────────────────────────────────────────────────────
            fixer_summary = (
                signals.extract_summary(_fixer_output)
                or signals.extract_commit_message(_fixer_output, fallback="")
            )
            commit_msg = signals.extract_commit_message(
                _fixer_output, fallback=f"fix(edge): iteration {iteration}"
            )
            if not no_git and not no_commit:
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
            status_label = "changed" if (no_git or no_commit) else "committed"
            fixer_detail = fixer_summary or commit_msg
            disp.finish_phase("fixer", status=status_label, detail=fixer_detail,
                              duration=fixer_duration, success=True)
            iter_entry["fixer"] = {"status": status_label, "detail": fixer_detail}

            # ── Breaker phase ─────────────────────────────────────────────────
            disp.start_phase("breaker")
            breaker_start = time.monotonic()
            try:
                breaker_output = agent.run(break_text, verbose=verbose)
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
                runner_result = try_runner(iter_entry)
                if runner_result == "error":
                    stats["reason"] = "agent_error"
                    iteration_log.append(iter_entry)
                    break
                elif runner_result == "issues":
                    stats["reason"] = "issues"
                    iteration_log.append(iter_entry)
                    continue
                else:  # "clear" or "skip"
                    stats["reason"] = "clear"
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

        stats["elapsed"] = time.monotonic() - start_time

    # Live panel is fully closed before printing anything below
    display.print_summary(stats)

    # ── Write report ──────────────────────────────────────────────────────────
    try:
        report_path = report.write(stats, iteration_log, output_dir=prompt_path.parent)
        if not no_git and not no_commit and stats["fixes"] > 0:
            try:
                git.commit(f"etch: add run report {report_path.name}", paths=[str(report_path)])
            except GitError:
                pass  # report write is best-effort
        display.print_report_saved(report_path)
    except Exception:
        pass  # report is best-effort, never fail the run over it
