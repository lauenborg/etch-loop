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
    timeout: int = 300,
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

    # Write prompt to stdin and close it — run in thread to avoid blocking on full pipe buffer
    stdin_exc: list[Exception] = []

    def write_stdin() -> None:
        try:
            process.stdin.write(prompt)
            process.stdin.close()
        except OSError as exc:
            stdin_exc.append(exc)

    stdin_writer = threading.Thread(target=write_stdin, daemon=True)
    stdin_writer.start()
    stdin_writer.join(timeout=30)
    if stdin_writer.is_alive():
        process.kill()
        process.wait()
        raise AgentError("Timed out writing prompt to claude stdin")
    if stdin_exc:
        process.kill()
        process.wait()
        raise AgentError(f"Failed to write prompt to claude stdin: {stdin_exc[0]}") from stdin_exc[0]

    output_lines: list[str] = []
    stderr_lines: list[str] = []
    lock = threading.Lock()

    def read_stdout() -> None:
        for line in process.stdout:
            with lock:
                output_lines.append(line)
            if verbose:
                print(line, end="", flush=True)
            if tick_callback is not None:
                tick_callback(line)

    def read_stderr() -> None:
        for line in process.stderr:
            stderr_lines.append(line)

    reader = threading.Thread(target=read_stdout, daemon=True)
    stderr_reader = threading.Thread(target=read_stderr, daemon=True)
    reader.start()
    stderr_reader.start()
    reader.join(timeout=timeout)
    if reader.is_alive():
        process.kill()
        process.wait()
        raise AgentError("claude subprocess timed out (output reader still running)")

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise AgentError("claude subprocess timed out waiting for exit")

    stderr_reader.join(timeout=10)

    stderr_output = "".join(stderr_lines).strip()

    if process.returncode != 0:
        detail = stderr_output or "(no stderr)"
        raise AgentError(
            f"claude exited with code {process.returncode}: {detail}"
        )

    return "".join(output_lines)
