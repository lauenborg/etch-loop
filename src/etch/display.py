"""Rich-based terminal UI for etch-loop."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, TypeVar

from rich.columns import Columns
from rich.console import Console, ConsoleOptions, RenderResult
from rich.live import Live
from rich.panel import Panel
from rich.segment import Segment
from rich.style import Style
from rich.table import Table
from rich.text import Text

_T = TypeVar("_T")

from etch import __version__

# ── Palette ───────────────────────────────────────────────────────────────────
BG = "#0a0a0a"
FG = "#e8e8e8"
DIM = "#555555"
AMBER = "#d4a547"
GREEN = "#7aba78"
RED = "#c96a6a"
BORDER = "#1e1e1e"

# ── Symbols (ASCII only) ──────────────────────────────────────────────────────
SYM_RUN = ">"
SYM_OK = "+"
SYM_FAIL = "x"
SYM_NEUTRAL = "-"

SCAN_WIDTH = 36
SCAN_BLOCK = "▓▒ "
SCAN_FILL = "░"
TICK_MS = 80


# ── ScanBar renderable ────────────────────────────────────────────────────────


class ScanBar:
    """Amber scan animation: ░░░▓▒ ░░░ block sliding left-to-right."""

    def __init__(self, tick: int) -> None:
        self.tick = tick

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        pos = self.tick % SCAN_WIDTH
        bar = list(SCAN_FILL * SCAN_WIDTH)
        for i, ch in enumerate(SCAN_BLOCK):
            bar[(pos + i) % SCAN_WIDTH] = ch
        yield Segment("".join(bar), Style(color=AMBER))


# ── EtchDisplay ───────────────────────────────────────────────────────────────


class EtchDisplay:
    """Terminal UI for etch-loop.

    History lines are printed immediately as static output.
    Live is used only for the currently-running scan line (transient=True),
    so terminal resizing cannot corrupt the output.
    """

    def __init__(self, target: str = "") -> None:
        self._console = Console(style=f"on {BG}")
        self._target = target
        self._stats: dict[str, Any] = {
            "iterations": 0,
            "fixes": 0,
            "issues": 0,
            "start": time.monotonic(),
        }
        self._live: Live | None = None
        self._current_phase = ""
        self._tick = 0
        self._lock = threading.Lock()
        self._ticker_stop = threading.Event()
        self._ticker_thread: threading.Thread | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def __enter__(self) -> "EtchDisplay":
        title = f"etch loop v{__version__}"
        if self._target:
            title += f"  {self._target}"
        self._console.print(f"\n  [{AMBER}]{title}[/{AMBER}]\n")
        return self

    def __exit__(self, *args: Any) -> None:
        self._stop_phase_live()

    # ── Public API ────────────────────────────────────────────────────────────

    def start_iteration(self, n: int) -> None:
        with self._lock:
            self._stats["iterations"] = n
        self._console.print(f"  [{DIM}]{SYM_NEUTRAL}  iteration {n}[/{DIM}]")

    def start_phase(self, phase: str) -> None:
        with self._lock:
            self._current_phase = phase
            self._tick = 0
        self._start_phase_live(phase)

    def finish_phase(
        self,
        phase: str,
        status: str,
        detail: str,
        duration: float,
        success: bool = True,
    ) -> None:
        self._stop_phase_live()
        color = GREEN if success else RED
        sym = SYM_OK if success else SYM_FAIL
        dur = _format_elapsed(duration)

        max_detail = 55
        if len(detail) > max_detail:
            detail = detail[: max_detail - 1] + "…"

        self._console.print(
            f"  [{color}]{sym}[/{color}]  "
            f"[{color}]{phase:<8}[/{color}]  "
            f"[{DIM}]{status:<11}[/{DIM}]  "
            f"[{FG}]{detail}[/{FG}]  "
            f"[{DIM}][{dur}][/{DIM}]"
        )

    def record_fix(self) -> None:
        with self._lock:
            self._stats["fixes"] += 1

    def record_issue(self) -> None:
        with self._lock:
            self._stats["issues"] += 1

    def print_summary(self, stats: dict[str, Any]) -> None:
        self._stop_phase_live()

        reason = stats.get("reason", "done")
        elapsed = stats.get("elapsed", 0.0)
        iterations = stats.get("iterations", 0)
        fixes = stats.get("fixes", 0)
        issues = stats.get("issues", 0)
        elapsed_str = _format_elapsed(elapsed)

        if reason == "clear":
            title = f"[{GREEN}]+ all clear[/{GREEN}]"
        elif reason == "no_changes":
            title = f"[{GREEN}]+ clean — fixer found nothing[/{GREEN}]"
        elif reason == "max_iterations":
            title = f"[{AMBER}]- stopped (max iterations)[/{AMBER}]"
        elif reason == "interrupted":
            title = f"[{AMBER}]- interrupted[/{AMBER}]"
        else:
            title = f"[{FG}]done[/{FG}]"

        body = (
            f"[{DIM}]iterations[/{DIM}]    [{FG}]{iterations}[/{FG}]\n"
            f"[{DIM}]fixes[/{DIM}]         [{FG}]{fixes}[/{FG}]\n"
            f"[{DIM}]breaker issues[/{DIM}] [{FG}]{issues}[/{FG}]\n"
            f"[{DIM}]elapsed[/{DIM}]       [{FG}]{elapsed_str}[/{FG}]"
        )

        self._console.print(
            Panel(
                body,
                title=title,
                border_style=Style(color=BORDER),
                style=Style(bgcolor=BG),
            )
        )

    # ── Phase Live management ─────────────────────────────────────────────────

    def _start_phase_live(self, phase: str) -> None:
        self._ticker_stop.clear()
        self._live = Live(
            self._render_scan(phase, 0),
            console=self._console,
            refresh_per_second=15,
            transient=True,   # erases itself cleanly on stop — no resize artifacts
        )
        self._live.__enter__()
        self._ticker_thread = threading.Thread(target=self._ticker_loop, daemon=True)
        self._ticker_thread.start()

    def _stop_phase_live(self) -> None:
        self._ticker_stop.set()
        if self._ticker_thread is not None:
            self._ticker_thread.join(timeout=1.0)
            self._ticker_thread = None
        if self._live is not None:
            self._live.__exit__(None, None, None)
            self._live = None

    def _render_scan(self, phase: str, tick: int) -> Table:
        table = Table.grid(padding=(0, 1))
        table.add_column(width=2)
        table.add_column(width=10)
        table.add_column(width=11)
        table.add_column()
        table.add_row(
            Text(f"  {SYM_RUN}", style=Style(color=AMBER)),
            Text(phase, style=Style(color=AMBER)),
            Text("running", style=Style(color=DIM)),
            ScanBar(tick),
        )
        return table

    def _ticker_loop(self) -> None:
        while not self._ticker_stop.is_set():
            with self._lock:
                self._tick += 1
                tick = self._tick
                phase = self._current_phase
            if self._live is not None:
                self._live.update(self._render_scan(phase, tick))
            time.sleep(TICK_MS / 1000.0)


# ── Standalone helpers ────────────────────────────────────────────────────────

_console = Console(style=f"on {BG}")


def run_with_scan(label: str, fn: Callable[[], _T]) -> _T:
    """Run fn() while showing a scan animation. Returns fn()'s result."""
    result: list[_T] = []
    error: list[BaseException] = []
    done = threading.Event()

    def worker() -> None:
        try:
            result.append(fn())
        except BaseException as exc:
            error.append(exc)
        finally:
            done.set()

    threading.Thread(target=worker, daemon=True).start()

    tick = 0
    with Live(console=_console, refresh_per_second=12, transient=True) as live:
        while not done.wait(timeout=TICK_MS / 1000.0):
            live.update(Columns([
                Text(f"{SYM_RUN}  {label}  ", style=Style(color=AMBER)),
                ScanBar(tick),
            ]))
            tick += 1

    _console.print(f"[{GREEN}]{SYM_OK}[/{GREEN}]  [{FG}]{label}[/{FG}]")

    if error:
        raise error[0]
    return result[0]


def print_dry_run(prompt_text: str) -> None:
    _console.print(
        Panel(
            Text(prompt_text, style=Style(color=FG)),
            title=f"[{AMBER}]dry run — prompt preview[/{AMBER}]",
            border_style=Style(color=BORDER),
            style=Style(bgcolor=BG),
        )
    )


def print_interrupted() -> None:
    _console.print(
        Panel(
            Text("run interrupted by user.", style=Style(color=AMBER)),
            title=f"[{AMBER}]- interrupted[/{AMBER}]",
            border_style=Style(color=BORDER),
            style=Style(bgcolor=BG),
        )
    )


def print_error(message: str) -> None:
    _console.print(
        Panel(
            Text(message, style=Style(color=RED)),
            title=f"[{RED}]x error[/{RED}]",
            border_style=Style(color=BORDER),
            style=Style(bgcolor=BG),
        )
    )


def print_analyzing() -> None:
    _console.print(f"[{AMBER}]{SYM_RUN}[/{AMBER}]  [{DIM}]analyzing codebase...[/{DIM}]")


def print_init_ok(filename: str) -> None:
    _console.print(f"[{GREEN}]{SYM_OK}[/{GREEN}]  [{FG}]{filename}[/{FG}]")


def print_init_skip(filename: str) -> None:
    _console.print(
        f"[{AMBER}]{SYM_NEUTRAL}[/{AMBER}]  [{DIM}]{filename} already exists, skipping[/{DIM}]"
    )


# ── Utilities ─────────────────────────────────────────────────────────────────


def _format_elapsed(seconds: float) -> str:
    seconds = max(0.0, seconds)
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    if mins > 0:
        return f"{mins}m {secs}s"
    return f"{secs}s"
