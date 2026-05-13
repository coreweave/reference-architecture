"""Remote Execution Helpers for running commands on remote hosts via SSH.

Usage:
    from arena.remote_execution_helpers import run_remote, ssh_command, ssh, shell

    # Run a command and get output
    result = run_remote("sinfo")

    # Quick one-liner for remote
    output = ssh("hostname")

    # Quick one-liner for local shell
    shell("aws s3 ls")

    # Get the SSH command string to run manually
    cmd = ssh_command("htop")
"""

import os
import shlex
import subprocess
import sys

# SSH Configuration (from environment or defaults)
SSH_KEY = os.getenv("CW_ARENA_SSH_KEY_PATH", "/root/.ssh/id_rsa")
SSH_HOST = os.getenv("CW_ARENA_SSH_HOST", "")


def ssh_command(
    command: str,
    interactive: bool = True,
    allocate_tty: bool = True,
) -> str:
    """Build an SSH command string for the remote host.

    Args:
        command: The command to run on the remote host
        interactive: If True, use -t for pseudo-terminal allocation (interactive mode)
        allocate_tty: If True, force tty allocation with -tt (useful for sudo commands)

    Returns:
        The full SSH command string
    """
    ssh_flags = ["-i", SSH_KEY]

    if allocate_tty:
        ssh_flags.append("-tt")  # Force pseudo-terminal allocation
    elif interactive:
        ssh_flags.append("-t")  # Request pseudo-terminal

    flags_str = " ".join(ssh_flags)
    escaped_command = shlex.quote(command)

    return f"ssh {flags_str} {SSH_HOST} {escaped_command}"


def run_remote(
    command: str,
    interactive: bool = True,
    capture_output: bool = True,
    timeout: int | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """Run a command on the remote host via SSH.

    Args:
        command: The command to run on the remote host
        interactive: If True, allocate a pseudo-terminal
        capture_output: If True, capture stdout and stderr
        timeout: Timeout in seconds (None for no timeout)
        check: If True, raise CalledProcessError on non-zero exit

    Returns:
        subprocess.CompletedProcess with returncode, stdout, stderr

    Example:
        result = run_remote("sinfo")
        print(result.stdout)
    """
    ssh_cmd = ssh_command(command, interactive=interactive, allocate_tty=False)

    return subprocess.run(
        ssh_cmd,
        shell=True,
        capture_output=capture_output,
        text=True,
        timeout=timeout,
        check=check,
    )


def run_remote_interactive(command: str) -> int:
    """Run a command interactively on the remote host (with full TTY).

    This is useful for commands that require user interaction like
    editors, htop, or anything that needs a proper terminal.

    Args:
        command: The command to run on the remote host

    Returns:
        The exit code of the command
    """
    ssh_cmd = ssh_command(command, interactive=True, allocate_tty=True)

    result = subprocess.run(ssh_cmd, shell=True)
    return result.returncode


def run_remote_stream(
    command: str,
    interactive: bool = False,
) -> subprocess.Popen:
    """Run a command on the remote host and stream output in real-time.

    Args:
        command: The command to run on the remote host
        interactive: If True, allocate a pseudo-terminal

    Returns:
        subprocess.Popen object for streaming stdout/stderr

    Example:
        proc = run_remote_stream("tail -f /var/log/syslog")
        for line in proc.stdout:
            print(line, end='')
    """
    ssh_cmd = ssh_command(command, interactive=interactive, allocate_tty=False)

    return subprocess.Popen(
        ssh_cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def ssh(command: str, verbose: bool = True, stream: bool = False) -> str:
    """Quick helper to run a command and return stdout.

    Handles errors gracefully by printing them instead of raising exceptions.

    Args:
        command: The command to run on the remote host
        verbose: If True, print errors to stderr (default True)
        stream: If True, stream output line-by-line in real-time.
                Note: In Marimo notebooks, streaming may still buffer until
                cell completion due to Marimo's output capture mechanism.

    Returns:
        The stdout output as a string (empty string on error)

    Example:
        output = ssh("hostname")
        print(output)  # prints the remote hostname

        # Stream long-running commands
        ssh("tail -f /var/log/syslog", stream=True)
    """
    if stream:
        # Set unbuffered mode for better streaming
        os.environ["PYTHONUNBUFFERED"] = "1"

        # Stream output in real-time
        ssh_cmd = ssh_command(command, interactive=False, allocate_tty=False)

        proc = subprocess.Popen(
            ssh_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=0,  # Unbuffered
        )

        output_lines = []
        if proc.stdout:
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                sys.stdout.write(line)
                sys.stdout.flush()
                output_lines.append(line)

        proc.wait()

        if proc.returncode != 0 and verbose:
            sys.stderr.write(f"\n[SSH] Exit code: {proc.returncode}\n")
            sys.stderr.flush()

        return "".join(output_lines)

    else:
        result = run_remote(command, interactive=False, capture_output=True)

        if result.returncode != 0:
            if verbose:
                print(f"[SSH Error] Command: {command}", file=sys.stderr)
                print(f"[SSH Error] Exit code: {result.returncode}", file=sys.stderr)
                if result.stderr:
                    print(f"[SSH Error] {result.stderr.strip()}", file=sys.stderr)
            return ""

        return result.stdout


class ShellResult(str):
    """String-like result from shell()/bash() that also carries structured fields.

    Subclasses str so existing callers that treat the return value as a string
    keep working. New callers can read .returncode, .stderr, .ok, .command for
    structured access.
    """

    returncode: int
    stderr: str
    command: str
    ok: bool

    def __new__(
        cls,
        stdout: str,
        *,
        returncode: int = 0,
        stderr: str = "",
        command: str = "",
        ok: bool = True,
    ) -> "ShellResult":
        """Create a string result with subprocess metadata attached."""
        instance = super().__new__(cls, stdout)
        instance.returncode = returncode
        instance.stderr = stderr
        instance.command = command
        instance.ok = ok
        return instance

    def __bool__(self) -> bool:
        """Treat failed commands as false while preserving string truthiness for stdout."""
        return self.ok and len(self) > 0


def shell(  # noqa: C901
    command: str | list,
    quiet: bool = False,
    check: bool = False,
    stream: bool = False,
    timeout: int | None = None,
    input: str | None = None,
) -> ShellResult:
    """Run a local shell command with clean output.

    Returns a ShellResult — a str subclass equal to the captured stdout, with
    .returncode, .stderr, .ok, .command for callers that need structured access.

    Args:
        command: Command string or list of arguments
        quiet: If True, suppress status messages (only show command output)
        check: If True, raise exception on non-zero exit code
        stream: If True, stream stdout/stderr in real-time (for long-running commands).
                Note: In Marimo notebooks, streaming may still buffer until
                cell completion due to Marimo's output capture mechanism.
        timeout: Optional timeout in seconds (non-stream mode only). On timeout
                 the result has returncode=124 and ok=False.
        input: Optional string piped to the command's stdin (non-stream mode only).

    Example:
        result = shell("aws s3 ls")
        if not result.ok:
            print(result.stderr)

        shell(["kubectl", "get", "pods"])
        shell("kubectl apply -f -", input=manifest_yaml)
        shell("s5cmd cp ...", stream=True)
    """
    if isinstance(command, str):
        cmd_display = command
        shell_mode = True
    else:
        cmd_display = " ".join(command)
        shell_mode = False

    if stream:
        # Set unbuffered mode for better streaming
        os.environ["PYTHONUNBUFFERED"] = "1"

        # Stream output in real-time
        if not quiet:
            sys.stdout.write(f"▶ {cmd_display}\n")
            sys.stdout.flush()

        proc = subprocess.Popen(
            command,
            shell=shell_mode,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Merge stderr into stdout
            text=True,
            bufsize=0,  # Unbuffered
        )

        # Stream output line by line
        output_lines = []
        if proc.stdout:
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                sys.stdout.write(line)
                sys.stdout.flush()
                output_lines.append(line)

        proc.wait()
        stdout = "".join(output_lines)

        if proc.returncode == 0:
            if not quiet:
                sys.stdout.write("✓ Done (exit: 0)\n")
                sys.stdout.flush()
        else:
            if not quiet:
                sys.stdout.write(f"✗ Failed (exit: {proc.returncode})\n")
                sys.stdout.flush()
            if check:
                raise subprocess.CalledProcessError(proc.returncode, command)

        return ShellResult(
            stdout,
            returncode=proc.returncode,
            stderr="",
            command=cmd_display,
            ok=proc.returncode == 0,
        )

    try:
        result = subprocess.run(
            command,
            shell=shell_mode,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input,
        )
    except subprocess.TimeoutExpired as err:
        out = err.stdout or ""
        err_text = err.stderr or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", errors="replace")
        if isinstance(err_text, bytes):
            err_text = err_text.decode("utf-8", errors="replace")
        stderr_msg = f"Command timed out after {timeout}s. {err_text.strip()}".strip()
        if not quiet:
            print(f"✗ {cmd_display}")
            print(f"  Error: {stderr_msg}")
        if check:
            raise
        return ShellResult(
            out,
            returncode=124,
            stderr=stderr_msg,
            command=cmd_display,
            ok=False,
        )

    if result.returncode == 0:
        if not quiet:
            print(f"✓ {cmd_display}")
        if result.stdout.strip():
            print(result.stdout.rstrip())
        return ShellResult(
            result.stdout,
            returncode=0,
            stderr=result.stderr,
            command=cmd_display,
            ok=True,
        )

    if not quiet:
        print(f"✗ {cmd_display}")
        if result.stderr.strip():
            print(f"  Error: {result.stderr.strip()}")
    if check:
        raise subprocess.CalledProcessError(result.returncode, command)
    return ShellResult(
        result.stdout,
        returncode=result.returncode,
        stderr=result.stderr,
        command=cmd_display,
        ok=False,
    )


def bash(
    command: str,
    quiet: bool = False,
    stream: bool = False,
    timeout: int | None = None,
    input: str | None = None,
) -> ShellResult:
    """Alias for shell() - run a bash command.

    Example:
        bash("echo Hello")
        bash("aws s3 ls")
        bash("s5cmd cp ...", stream=True)
    """
    return shell(command, quiet=quiet, stream=stream, timeout=timeout, input=input)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        print(f"Running: {cmd}")
        result = run_remote(cmd)
        print(result.stdout)
        if result.stderr:
            print(f"STDERR: {result.stderr}", file=sys.stderr)
        sys.exit(result.returncode)
    else:
        print("Usage: python -m arena.remote_execution_helpers <command>")
        print("Example: python -m arena.remote_execution_helpers 'sinfo'")
