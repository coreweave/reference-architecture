#!/usr/bin/env python3
"""Create a sandbox, sign in to Claude Code, and run `claude remote-control`.
"""

from __future__ import annotations

import fcntl
import os
import signal
import struct
import sys
import termios
import threading
import tty

os.environ.setdefault("WANDB_SILENT", "true")

from wandb.sandbox import NetworkOptions, ResourceOptions, Sandbox, SandboxDefaults  # noqa: E402

# Pre-seeding ~/.claude.json marks /workspace as trusted and skips first-run onboarding
CLAUDE_JSON = '{"hasCompletedOnboarding": true, "projects": {"/workspace": {"hasTrustDialogAccepted": true}}}'
BOOTSTRAP = (
    "npm install -g @anthropic-ai/claude-code --silent "
    "&& mkdir -p /workspace "
    f"&& printf '%s' '{CLAUDE_JSON}' > ~/.claude.json"
)
# Sign in first (full-scope claude.ai session, stored in the pod's ~/.claude),
# then serve Remote Control from /workspace.
RUN = "claude auth login && cd /workspace && exec claude remote-control"


def terminal_size() -> tuple[int, int]:
    try:
        rows, cols = struct.unpack("hh", fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\0" * 4))
        return cols or 100, rows or 30
    except (OSError, struct.error):
        return 100, 30


def attach(sandbox: Sandbox, command: list[str]) -> int:
    """Bridge the local terminal to a PTY inside the sandbox."""
    cols, rows = terminal_size()
    session = sandbox.shell(command, width=cols, height=rows)

    def pump_output() -> None:
        try:
            for chunk in session.output:
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
        except Exception:  # noqa: BLE001 - session closing is the normal exit path
            pass

    threading.Thread(target=pump_output, daemon=True).start()

    def on_resize(*_: object) -> None:
        new_cols, new_rows = terminal_size()
        try:
            session.resize(new_cols, new_rows)
        except Exception:  # noqa: BLE001 - resize is cosmetic
            pass

    signal.signal(signal.SIGWINCH, on_resize)

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            data = os.read(fd, 1024)
            if not data:
                break
            try:
                session.stdin.write(data).result()
            except Exception:  # noqa: BLE001 - remote session ended; stop forwarding
                break
    except (OSError, KeyboardInterrupt):
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)

    try:
        return session.wait(timeout=10)
    except Exception:  # noqa: BLE001
        return 0


def main() -> int:
    print("Creating sandbox...", flush=True)
    sandbox = Sandbox.run(
        defaults=SandboxDefaults(
            container_image="node:22",
            tags=("claude-code", "remote-control"),
            resources=ResourceOptions(requests={"cpu": "2", "memory": "4Gi"}),
        ),
        network=NetworkOptions(egress_mode="internet"),
        max_lifetime_seconds=4 * 3600,
    )
    sandbox.wait()
    print(f"  {sandbox.sandbox_id} (expires in 4h)", flush=True)

    print("Installing Claude Code...", flush=True)
    setup = sandbox.exec(["bash", "-lc", BOOTSTRAP], timeout_seconds=900)
    setup.wait(timeout=900)
    if setup.returncode != 0:
        sys.stderr.write(setup.result().stderr_bytes.decode(errors="replace"))
        sandbox.stop(missing_ok=True).result()
        return 1

    print("Sign in when prompted, then Remote Control starts. Ctrl-C stops it.\n", flush=True)
    code = attach(sandbox, ["bash", "-lc", RUN])

    print("\nStopping sandbox...", flush=True)
    sandbox.stop(missing_ok=True).result()
    return code


if __name__ == "__main__":
    sys.exit(main())
