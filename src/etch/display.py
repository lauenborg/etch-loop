"""Rich-based terminal UI for etch-loop."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from rich.columns import Columns
from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.live import Live
from rich.panel import Panel
from rich.segment import Segment
from rich.style import Style
from rich.table import Table
from rich.text import Text

_T = TypeVar("_T")

from etch import __version__

# ── Palette ──────────────────────────────────────────────────────────────────
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

SCAN_WIDTH = 40
SCAN_BLOCK = "▓▒ "  # 3-char block
SCAN_FILL = "░"
TICK_MS = 80


# ── ScanBar renderable ────────────────────────────────────────────────────────


class ScanBar:
    """A Rich renderable that renders one frame of the scan animation.

    The bar is SCAN_WIDTH chars wide, filled with SCAN_FILL (░).
    A 3-char SCAN_BLOCK (▓▒ ) slides left-to-right, wrapping at the end.
    Rendered in amber.
    """

    def __init__(self, tick: int) -> None:
        self.tick = tick

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        width = SCAN_WIDTH
        block = SCAN_BLOCK
        block_len = len(block)
        pos = self.tick % width

        bar = list(SCAN_FILL * width)
        for i, ch in enumerate(block):
            idx = (pos + i) % width
            bar[idx] = ch

        yield Segment("".join(bar), Style(color=AMBER))


# ── Log entry dataclass ───────────────────────────────────────────────────────


@dataclass
class _LogEntry:
    """One line in the scrolling log."""

    symbol: str
    phase: str
    status: str
    detail: str | RenderableType
    color: str
    running: bool = False
    tick: int = 0


# ── EtchDisplay ──────────────────────────────────────────────────────────────


class EtchDisplay:
    """Manages the Rich Live layout for the etch-loop run."""

    def __init__(self, target: str = "") -> None:
        self._console = Console(style=f"on {BG}")
        self._target = target
        self._entries: list[_LogEntry] = []
        self._stats: dict[str, Any] = {
            "iterations": 0,
            "fixes": 0,
            "issues": 0,
            "start": time.monotonic(),
        }
        self._live: Live | None = None
        self._tick = 0
        self._ticker_stop = threading.Event()
        self._ticker_thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # ── Public lifecycle ──────────────────────────────────────────────────────

    def __enter__(self) -> "EtchDisplay":
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=15,
            transient=False,
        )
        self._live.__enter__()
        self._start_ticker()
        return self

    def __exit__(self, *args: Any) -> None:
        self._stop_ticker()
        if self._live is not None:
            self._live.__exit__(*args)

    # ── Iteration / phase API ─────────────────────────────────────────────────

    def start_iteration(self, n: int) -> None:
        """Add an iteration header line to the log."""
        with self._lock:
            self._stats["iterations"] = n
            self._entries.append(
                _LogEntry(
                    symbol=SYM_NEUTRAL,
                    phase="iteration",
                    status=str(n),
                    detail="",
                    color=DIM,
                )
            )
        self._refresh()

    def start_phase(self, phase: str) -> None:
        """Add a 'running' line with scan animation for the given phase."""
        with self._lock:
            self._entries.append(
                _LogEntry(
                    symbol=SYM_RUN,
                    phase=phase,
                    status="running",
                    detail=ScanBar(self._tick),
                    color=AMBER,
                    running=True,
                    tick=self._tick,
                )
            )
        self._refresh()

    def finish_phase(
        self,
        phase: str,
        status: str,
        detail: str,
        duration: float,
        success: bool = True,
    ) -> None:
        """Replace the last running line for `phase` with a finished result."""
        color = GREEN if success else RED
        symbol = SYM_OK if success else SYM_FAIL
        dur_str = f"{duration:.1f}s"

        with self._lock:
            # Find the last running entry for this phase and replace it
            for i in range(len(self._entries) - 1, -1, -1):
                entry = self._entries[i]
                if entry.phase == phase and entry.running:
                    self._entries[i] = _LogEntry(
                        symbol=symbol,
                        phase=phase,
                        status=status,
                        detail=detail,
                        color=color,
                        running=False,
                    )
                    break
        self._refresh()

    def record_fix(self) -> None:
        """Increment the fix counter."""
        with self._lock:
            self._stats["fixes"] += 1

    def record_issue(self) -> None:
        """Increment the breaker-issues counter."""
        with self._lock:
            self._stats["issues"] += 1

    def print_summary(self, stats: dict[str, Any]) -> None:
        """Print the final done/stopped/interrupted panel."""
        self._stop_ticker()
        if self._live is not None:
            self._live.stop()

        reason = stats.get("reason", "done")
        elapsed = stats.get("elapsed", 0.0)
        iterations = stats.get("iterations", 0)
        fixes = stats.get("fixes", 0)
        issues = stats.get("issues", 0)

        elapsed_str = _format_elapsed(elapsed)

        if reason == "clear":
            title_color = GREEN
            title = f"[{GREEN}]+ all clear[/{GREEN}]"
        elif reason == "interrupted":
            title_color = AMBER
            title = f"[{AMBER}]- interrupted[/{AMBER}]"
        elif reason == "max_iterations":
            title_color = AMBER
            title = f"[{AMBER}]- stopped (max iterations)[/{AMBER}]"
        elif reason == "no_changes":
            title_color = GREEN
            title = f"[{GREEN}]+ clean — fixer found nothing[/{GREEN}]"
        else:
            title_color = FG
            title = f"[{FG}]done[/{FG}]"

        body = (
            f"[{DIM}]iterations[/{DIM}] [{FG}]{iterations}[/{FG}]   "
            f"[{DIM}]fixes[/{DIM}] [{FG}]{fixes}[/{FG}]   "
            f"[{DIM}]breaker issues[/{DIM}] [{FG}]{issues}[/{FG}]   "
            f"[{DIM}]{elapsed_str} elapsed[/{DIM}]"
        )

        panel = Panel(
            body,
            title=title,
            border_style=Style(color=BORDER),
            style=Style(bgcolor=BG),
        )
        self._console.print(panel)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self) -> RenderableType:
        """Build the full Live renderable."""
        with self._lock:
            entries = list(self._entries)
            tick = self._tick
            stats = dict(self._stats)

        elapsed = time.monotonic() - stats["start"]

        # Build log table
        log_table = Table.grid(padding=(0, 1))
        log_table.add_column(width=2)  # symbol
        log_table.add_column(width=10)  # phase
        log_table.add_column(width=12)  # status
        log_table.add_column()  # detail

        for entry in entries:
            if entry.running:
                detail_render: RenderableType = ScanBar(tick)
            else:
                detail_render = Text(str(entry.detail), style=Style(color=DIM))

            sym_text = Text(entry.symbol, style=Style(color=entry.color))
            phase_text = Text(entry.phase, style=Style(color=entry.color))
            status_text = Text(entry.status, style=Style(color=DIM))

            log_table.add_row(sym_text, phase_text, status_text, detail_render)

        # Header
        title_str = f"etch loop v{__version__}"
        if self._target:
            title_str += f"  {self._target}"

        # Stats footer
        elapsed_str = _format_elapsed(elapsed)
        footer = (
            f"[{DIM}]iterations[/{DIM}] [{FG}]{stats['iterations']}[/{FG}]   "
            f"[{DIM}]fixes[/{DIM}] [{FG}]{stats['fixes']}[/{FG}]   "
            f"[{DIM}]breaker issues[/{DIM}] [{FG}]{stats['issues']}[/{FG}]   "
            f"[{DIM}]{elapsed_str} elapsed[/{DIM}]"
        )

        panel = Panel(
            log_table,
            title=f"[{AMBER}]{title_str}[/{AMBER}]",
            subtitle=footer,
            border_style=Style(color=BORDER),
            style=Style(bgcolor=BG),
        )
        return panel

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._render())

    # ── Ticker thread ─────────────────────────────────────────────────────────

    def _start_ticker(self) -> None:
        self._ticker_stop.clear()
        self._ticker_thread = threading.Thread(
            target=self._ticker_loop, daemon=True
        )
        self._ticker_thread.start()

    def _stop_ticker(self) -> None:
        self._ticker_stop.set()
        if self._ticker_thread is not None:
            self._ticker_thread.join(timeout=1.0)
            self._ticker_thread = None

    def _ticker_loop(self) -> None:
        while not self._ticker_stop.is_set():
            with self._lock:
                self._tick += 1
            self._refresh()
            time.sleep(TICK_MS / 1000.0)


# ── Standalone print helpers (used outside Live context) ──────────────────────

_console = Console(style=f"on {BG}")


def print_dry_run(prompt_text: str) -> None:
    """Print the prompt in a panel for --dry-run mode."""
    _console.print(
        Panel(
            Text(prompt_text, style=Style(color=FG)),
            title=f"[{AMBER}]dry run — prompt preview[/{AMBER}]",
            border_style=Style(color=BORDER),
            style=Style(bgcolor=BG),
        )
    )


def print_interrupted() -> None:
    """Print interrupted notice."""
    _console.print(
        Panel(
            Text("Run interrupted by user.", style=Style(color=AMBER)),
            title=f"[{AMBER}]- interrupted[/{AMBER}]",
            border_style=Style(color=BORDER),
            style=Style(bgcolor=BG),
        )
    )


def print_error(message: str) -> None:
    """Print an error panel."""
    _console.print(
        Panel(
            Text(message, style=Style(color=RED)),
            title=f"[{RED}]x error[/{RED}]",
            border_style=Style(color=BORDER),
            style=Style(bgcolor=BG),
        )
    )


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
    with Live(console=_console, refresh_per_second=12) as live:
        while not done.wait(timeout=TICK_MS / 1000.0):
            label_text = Text(f"{SYM_RUN}  {label}  ", style=Style(color=AMBER))
            live.update(Columns([label_text, ScanBar(tick)]))
            tick += 1
        live.update(Text(f"{SYM_OK}  {label}", style=Style(color=GREEN)))

    if error:
        raise error[0]
    return result[0]


def print_analyzing() -> None:
    """Print a status line while etch init analyzes the codebase."""
    _console.print(f"[{AMBER}]{SYM_RUN}[/{AMBER}]  [{DIM}]analyzing codebase...[/{DIM}]")


def print_init_ok(filename: str) -> None:
    """Print a success line for etch init."""
    _console.print(f"[{GREEN}]{SYM_OK}[/{GREEN}]  [{FG}]{filename}[/{FG}]")


def print_init_skip(filename: str) -> None:
    """Print a skip line for etch init (file already exists)."""
    _console.print(
        f"[{AMBER}]{SYM_NEUTRAL}[/{AMBER}]  [{DIM}]{filename} already exists, skipping[/{DIM}]"
    )


# ── Utilities ─────────────────────────────────────────────────────────────────


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as '2m 14s' or '45s'."""
    seconds = max(0.0, seconds)
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    if mins > 0:
        return f"{mins}m {secs}s"
    return f"{secs}s"
