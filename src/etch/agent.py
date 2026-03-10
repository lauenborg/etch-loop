"""Claude agent subprocess runner."""

import subprocess
import threading
from collections.abc import Callable


class AgentError(Exception):
    """Raised when the agent subprocess fails or is unavailable."""


def run(
    prompt: str,
    verbose: bool = False,
    tick_callback: Callable[[str], None] | None = None,
) -> str:
    """Run the Claude agent with the given prompt piped to stdin.

    Launches `claude -p --dangerously-skip-permissions` as a subprocess,
    pipes `prompt` to its stdin, and returns the full stdout.

    Args:
        prompt: The prompt text to send to Claude.
        verbose: If True, streams output to terminal in addition to capturing it.
        tick_callback: Optional callable called with each line of output as it
                       arrives. Used by display layer for streaming updates.

    Returns:
        The full stdout output from the agent as a string.

    Raises:
        AgentError: If `claude` is not found, or exits with a non-zero code.
    """
    cmd = ["claude", "-p", "--dangerously-skip-permissions"]

    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        raise AgentError(
            "claude executable not found. "
            "Is Claude Code installed? Run: npm install -g @anthropic-ai/claude-code"
        )
    except OSError as exc:
        raise AgentError(f"Failed to launch claude: {exc}") from exc

    # Write prompt to stdin and close it
    try:
        process.stdin.write(prompt)
        process.stdin.close()
    except BrokenPipeError as exc:
        raise AgentError(f"Failed to write prompt to claude stdin: {exc}") from exc

    output_lines: list[str] = []
    lock = threading.Lock()

    def read_stdout() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            with lock:
                output_lines.append(line)
            if verbose:
                print(line, end="", flush=True)
            if tick_callback is not None:
                tick_callback(line)

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    reader.join()

    process.wait()

    # Capture stderr for error reporting
    stderr_output = ""
    if process.stderr:
        stderr_output = process.stderr.read().strip()

    if process.returncode != 0:
        detail = stderr_output or "(no stderr)"
        raise AgentError(
            f"claude exited with code {process.returncode}: {detail}"
        )

    return "".join(output_lines)
