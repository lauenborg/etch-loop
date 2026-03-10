"""CLI entry points for etch-loop."""

from __future__ import annotations

from pathlib import Path

import typer

from etch import agent, analyze, display, loop
from etch.agent import AgentError

app = typer.Typer(
    name="etch",
    help="Run Claude Code in a fix-break loop, hunting for edge cases.",
    add_completion=False,
    pretty_exceptions_show_locals=False,
)


@app.command()
def init() -> None:
    """Analyze the codebase with Claude and write tailored SCAN.md, ETCH.md, BREAK.md."""
    root = Path.cwd()
    etch_dir = root / "etch-loop"
    etch_dir.mkdir(exist_ok=True)
    info = analyze.analyze(root)
    init_prompt = analyze.build_init_prompt(info)

    agent_scope: str | None = None
    with display.InitDisplay() as disp:
        disp.start_scan()
        try:
            agent_scope = agent.run(init_prompt)
            disp.finish_scan(success=True)
        except AgentError as exc:
            disp.finish_scan(success=False)
            disp.add_line(display.SYM_NEUTRAL, display.DIM, f"falling back to static analysis ({exc})")

        for dest, content, label in [
            (etch_dir / "SCAN.md",  analyze.build_scan_md(info, agent_scope),  "etch-loop/SCAN.md"),
            (etch_dir / "ETCH.md",  analyze.build_etch_md(info, agent_scope),  "etch-loop/ETCH.md"),
            (etch_dir / "BREAK.md", analyze.build_break_md(info, agent_scope), "etch-loop/BREAK.md"),
            (etch_dir / "RUN.md",   analyze.build_run_md(info),                "etch-loop/RUN.md"),
        ]:
            if dest.exists():
                disp.add_line(display.SYM_NEUTRAL, display.DIM, f"{label} already exists, skipping")
            else:
                dest.write_text(content, encoding="utf-8")
                disp.add_line(display.SYM_OK, display.GREEN, label)


@app.command()
def run(
    focus: str = typer.Argument(
        default=None,
        help="Optional focus description, e.g. 'the auth module' or 'error handling in payments'.",
    ),
    prompt: str = typer.Option(
        "./etch-loop/ETCH.md",
        "--prompt",
        help="Path to the fixer prompt file (ETCH.md).",
        show_default=True,
    ),
    max_iterations: int = typer.Option(
        20,
        "--max-iterations",
        "-n",
        help="Maximum number of fix-break cycles.",
        show_default=True,
        min=1,
    ),
    no_commit: bool = typer.Option(
        False,
        "--no-commit",
        help="Skip git commits after fixer runs.",
        is_flag=True,
    ),
    no_git: bool = typer.Option(
        False,
        "--no-git",
        help="Disable all git operations (diff checks and commits).",
        is_flag=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the fixer prompt and exit without running.",
        is_flag=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Stream agent output to the terminal.",
        is_flag=True,
    ),
) -> None:
    """Run the fix-break loop against the current repository.

    Optionally pass a focus description to narrow the scan:

      etch run "the authentication module"

      etch run "error handling in the payments flow"
    """
    try:
        loop.run(
            prompt_path=prompt,
            max_iterations=max_iterations,
            no_commit=no_commit,
            no_git=no_git,
            dry_run=dry_run,
            verbose=verbose,
            focus=focus,
        )
    except KeyboardInterrupt:
        display.print_interrupted()
        raise typer.Exit(code=130)
