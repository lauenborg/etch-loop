"""CLI entry points for etch-loop."""

from __future__ import annotations

import importlib.resources
import shutil
from pathlib import Path
from typing import Optional

import typer

from etch import display, loop

app = typer.Typer(
    name="etch",
    help="Run Claude Code in a fix-break loop, hunting for edge cases.",
    add_completion=False,
    pretty_exceptions_show_locals=False,
)

_TEMPLATES = ["ETCH.md", "BREAK.md"]


@app.command()
def init() -> None:
    """Copy ETCH.md and BREAK.md templates into the current directory."""
    for filename in _TEMPLATES:
        dest = Path.cwd() / filename

        if dest.exists():
            display.print_init_skip(filename)
            continue

        try:
            # Python 3.9+ traversable API
            pkg_templates = importlib.resources.files("etch") / "templates" / filename
            content = pkg_templates.read_text(encoding="utf-8")
            dest.write_text(content, encoding="utf-8")
            display.print_init_ok(filename)
        except (FileNotFoundError, ModuleNotFoundError, TypeError) as exc:
            display.print_error(f"Could not copy {filename}: {exc}")


@app.command()
def run(
    prompt: str = typer.Option(
        "./ETCH.md",
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
    """Run the fix-break loop against the current repository."""
    try:
        loop.run(
            prompt_path=prompt,
            max_iterations=max_iterations,
            no_commit=no_commit,
            dry_run=dry_run,
            verbose=verbose,
        )
    except KeyboardInterrupt:
        display.print_interrupted()
        raise typer.Exit(code=130)
