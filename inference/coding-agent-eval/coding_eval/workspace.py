"""Per-attempt repository workspaces and the tools a coding agent can call in them.

Every attempt gets its own throwaway checkout of ``base_sha`` (a ``git clone
--shared`` of the cached mirror, so it is cheap and fully independent of other
attempts running in parallel). File tools are confined to that directory.

``run_command`` executes model-chosen shell commands, so it is restricted to
an allowlist of read-only programs by default. Set ``allow_any_command=True``
only when the workspace itself is isolated (a CoreWeave Sandbox or a throwaway
pod) — never on a machine holding credentials you care about.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_TOOL_OUTPUT = 12_000
HISTORY_DEPTH = 200  # commits of pre-task history kept in each workspace
# Only programs with no option that runs another program or writes a file. Tools such as
# awk, sed, find, rg, sort, tree, uniq and file are deliberately absent: each has options
# that execute commands or write output (system(), -exec, --pre, -o, ...). The search and
# list_files tools cover what they would be used for.
READ_ONLY_COMMANDS = {"ls", "cat", "head", "tail", "wc", "grep", "cut", "diff", "stat", "echo", "pwd", "git"}
READ_ONLY_GIT = {"status", "diff", "log", "show", "grep", "ls-files", "blame", "rev-parse"}
# git options that run a program or write a file, even under a read-only subcommand.
_GIT_DENIED_OPTIONS = (
    "--output", "--open-files-in-pager", "--ext-diff", "--textconv", "--exec", "--upload-pack", "--no-index",
)  # fmt: skip
_SHELL_META = re.compile(r"[;&|`$><]|\n")


class ToolError(Exception):
    """A tool call that failed in a way the model should see and recover from."""


def _check_git(argv: list[str]) -> None:
    """Allow only read-only git subcommands, without options that run programs or write files."""
    if len(argv) < 2 or argv[1] not in READ_ONLY_GIT:
        raise ToolError(f"only read-only git subcommands are allowed: {', '.join(sorted(READ_ONLY_GIT))}")
    for a in argv[2:]:
        if a.startswith(_GIT_DENIED_OPTIONS):
            raise ToolError(f"git option {a.split('=', 1)[0]!r} is not allowed here")
        # git grep -O / clustered short options such as -nO run a pager program.
        if argv[1] == "grep" and a.startswith("-") and not a.startswith("--") and "O" in a:
            raise ToolError("git grep -O (open files in a pager) is not allowed here")


def _truncate(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} characters]"


@dataclass
class Workspace:
    """A throwaway checkout of one task's starting commit, plus the tools that act on it."""

    root: Path
    base_sha: str
    read_only: bool = False
    allow_any_command: bool = False
    command_timeout_s: int = 60
    changed_paths: set[str] = field(default_factory=set)

    @classmethod
    def create(cls, mirror: Path, base_sha: str, **kwargs: Any) -> Workspace:
        """Create a repo at ``base_sha`` that contains NO later history.

        A plain clone would carry the repository's future, including the commit
        that merged this task's fix, and agents do find it (``git log --all -S``,
        ``git show <sha>``). So the workspace is a fresh repo with a shallow fetch
        of ``base_sha`` and its last ``HISTORY_DEPTH`` ancestors only: history
        before the task stays searchable, the answer does not exist in it.
        """
        root = Path(tempfile.mkdtemp(prefix="coding-eval-"))
        upload_pack = "git -c uploadpack.allowAnySHA1InWant=true upload-pack"
        for args in (
            ["git", "init", "--quiet", str(root)],
            ["git", "-C", str(root), "fetch", "--quiet", f"--depth={HISTORY_DEPTH}",
             f"--upload-pack={upload_pack}", f"file://{mirror}", base_sha],
            ["git", "-C", str(root), "checkout", "--quiet", "--detach", base_sha],
        ):  # fmt: skip
            result = subprocess.run(args, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                shutil.rmtree(root, ignore_errors=True)
                raise RuntimeError(f"workspace setup failed ({' '.join(args[:3])}): {result.stderr.strip()}")
        (root / ".git" / "FETCH_HEAD").unlink(missing_ok=True)  # it names the mirror's path
        return cls(root=root, base_sha=base_sha, **kwargs)

    def cleanup(self) -> None:
        """Delete the checkout."""
        shutil.rmtree(self.root, ignore_errors=True)

    # -- path safety -------------------------------------------------------

    def _resolve(self, path: str) -> Path:
        if not isinstance(path, str) or not path.strip():
            raise ToolError("path must be a non-empty string relative to the repository root")
        candidate = (self.root / path.strip().lstrip("/")).resolve()
        if candidate != self.root.resolve() and self.root.resolve() not in candidate.parents:
            raise ToolError(f"path {path!r} is outside the repository")
        if ".git" in candidate.relative_to(self.root.resolve()).parts:
            raise ToolError("the .git directory is off limits")
        return candidate

    def _rel(self, p: Path) -> str:
        return str(p.relative_to(self.root.resolve()))

    # -- tools -------------------------------------------------------------

    def list_files(self, path: str = ".", pattern: str | None = None, max_results: int = 300) -> str:
        """List tracked and untracked (non-ignored) files, optionally filtered by glob."""
        base = self._resolve(path or ".")
        if not base.exists():
            raise ToolError(f"{path} does not exist")
        if base.is_file():
            return self._rel(base)
        target = self._rel(base) if base != self.root.resolve() else "."
        args = ["git", "-C", str(self.root), "ls-files", "--cached", "--others", "--exclude-standard", "--", target]
        out = subprocess.run(args, capture_output=True, text=True, check=False).stdout.splitlines()
        if pattern:
            out = [f for f in out if fnmatch.fnmatch(f, pattern) or fnmatch.fnmatch(f.rsplit("/", 1)[-1], pattern)]
        extra = f"\n... {len(out) - max_results} more" if len(out) > max_results else ""
        return "\n".join(out[:max_results]) + extra if out else "(no files)"

    def read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> str:
        """Return a file (or line range) with line numbers."""
        p = self._resolve(path)
        if not p.is_file():
            raise ToolError(f"{path} is not a file")
        lines = p.read_text(errors="replace").splitlines()
        start = max(int(start_line or 1), 1)
        end = min(int(end_line or len(lines)), len(lines))
        numbered = "\n".join(f"{i:>6}\t{lines[i - 1]}" for i in range(start, end + 1))
        return _truncate(numbered or "(empty file)")

    def search(self, pattern: str, path: str = ".", max_results: int = 100) -> str:
        """Search file contents with ``git grep -E``."""
        if not pattern:
            raise ToolError("pattern is required")
        base = self._resolve(path or ".")
        args = [
            "git",
            "-C",
            str(self.root),
            "grep",
            "-n",
            "-I",
            "--untracked",
            "-E",
            pattern,
            "--",
            self._rel(base) if base != self.root.resolve() else ".",
        ]
        result = subprocess.run(args, capture_output=True, text=True, check=False)  # fmt: skip
        if result.returncode == 1:
            return "(no matches)"
        if result.returncode not in (0, 1):
            raise ToolError(result.stderr.strip() or "search failed")
        lines = result.stdout.splitlines()
        extra = f"\n... {len(lines) - max_results} more matches" if len(lines) > max_results else ""
        return _truncate("\n".join(lines[:max_results]) + extra)

    def write_file(self, path: str, content: str) -> str:
        """Create or overwrite a file."""
        if self.read_only:
            raise ToolError("this is a planning task; files must not be modified")
        if not isinstance(content, str):
            raise ToolError("content must be a string")
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        self.changed_paths.add(self._rel(p))
        return f"wrote {len(content.splitlines())} lines to {self._rel(p)}"

    def edit_file(self, path: str, old_str: str, new_str: str) -> str:
        """Replace one exact, unique occurrence of ``old_str``."""
        if self.read_only:
            raise ToolError("this is a planning task; files must not be modified")
        p = self._resolve(path)
        if not p.is_file():
            raise ToolError(f"{path} is not a file (use write_file to create it)")
        text = p.read_text(errors="replace")
        count = text.count(old_str) if old_str else 0
        if count == 0:
            raise ToolError("old_str was not found in the file; read the file and copy the text exactly")
        if count > 1:
            raise ToolError(f"old_str occurs {count} times; include more surrounding context so it is unique")
        p.write_text(text.replace(old_str, new_str, 1))
        self.changed_paths.add(self._rel(p))
        return f"edited {self._rel(p)}"

    def run_command(self, command: str) -> str:
        """Run a command in the repo root; read-only allowlist unless ``allow_any_command``."""
        if not isinstance(command, str) or not command.strip():
            raise ToolError("command is required")
        if not self.allow_any_command:
            if _SHELL_META.search(command):
                raise ToolError("pipes, redirects and command chaining are disabled in this workspace")
            try:
                argv = shlex.split(command)
            except ValueError as e:
                raise ToolError(f"could not parse command: {e}") from None
            if not argv:
                raise ToolError("command is required")
            self._check_read_only(argv)
            shell, args = False, argv
        else:
            shell, args = True, command
        try:
            result = subprocess.run(
                args, shell=shell, cwd=self.root, capture_output=True, text=True,
                timeout=self.command_timeout_s, check=False,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.root), "GIT_PAGER": "cat"},
            )  # fmt: skip
        except subprocess.TimeoutExpired:
            raise ToolError(f"command timed out after {self.command_timeout_s}s") from None
        out = (result.stdout + (("\n[stderr]\n" + result.stderr) if result.stderr else "")).strip()
        return _truncate(f"exit code {result.returncode}\n{out}")

    def _check_read_only(self, argv: list[str]) -> None:
        """Reject commands that could run programs, write files, or reach outside the workspace."""
        prog = argv[0]
        if prog not in READ_ONLY_COMMANDS:
            raise ToolError(f"{prog!r} is not allowed here; allowed: {', '.join(sorted(READ_ONLY_COMMANDS))}")
        if prog == "git":
            _check_git(argv)
        root = self.root.resolve()
        for a in argv[1:]:
            # Check the value of --opt=value as well as bare arguments.
            value = a.split("=", 1)[1] if a.startswith("-") and "=" in a else a
            if value.startswith(("/", "~")) or ".." in Path(value).parts:
                raise ToolError(f"argument {a!r} points outside the repository; use paths relative to its root")
            candidate = self.root / value
            if value and os.path.lexists(candidate):  # follows symlinks: a link out of the repo is rejected too
                resolved = candidate.resolve()
                if resolved != root and root not in resolved.parents:
                    raise ToolError(f"argument {a!r} resolves outside the repository")

    # -- results -----------------------------------------------------------

    def diff(self) -> str:
        """Unified diff of the working tree (including new files) against ``base_sha``."""
        subprocess.run(["git", "-C", str(self.root), "add", "-A", "-N"], capture_output=True, check=False)
        return subprocess.run(
            ["git", "-C", str(self.root), "diff", "-M", self.base_sha], capture_output=True, text=True, check=False
        ).stdout


# -- tool schemas ----------------------------------------------------------
# Provider-neutral JSON schemas; agent.py adapts them to OpenAI / Anthropic shapes.

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "list_files",
        "description": "List tracked files under a directory of the repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory relative to the repo root. Defaults to '.'"},
                "pattern": {"type": "string", "description": "Optional glob filter, e.g. '*.py'"},
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_file",
        "description": "Read a file, returned with line numbers. Optionally limit to a line range.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search",
        "description": "Search file contents with an extended regular expression (git grep). Returns path:line:text.",
        "parameters": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}},
            "required": ["pattern"],
            "additionalProperties": False,
        },
    },
    {
        "name": "edit_file",
        "description": "Replace one exact, unique occurrence of old_str with new_str in a file.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "old_str": {"type": "string"}, "new_str": {"type": "string"}},
            "required": ["path", "old_str", "new_str"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write_file",
        "description": "Create a file or overwrite it entirely with new content.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_command",
        "description": "Run a shell command in the repository root and return its output.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
            "additionalProperties": False,
        },
    },
    {
        "name": "finish",
        "description": "Call exactly once when the task is complete. Summarize the change (or give the full plan).",
        "parameters": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
    },
]
TOOL_NAMES = {t["name"] for t in TOOL_SPECS}
MUTATING_TOOLS = {"edit_file", "write_file"}


def validate_args(name: str, args: Any) -> str | None:
    """Return an error string if ``args`` does not satisfy the tool schema, else None."""
    spec = next((t for t in TOOL_SPECS if t["name"] == name), None)
    if spec is None:
        return f"unknown tool {name!r}"
    if not isinstance(args, dict):
        return "arguments must be a JSON object"
    props = spec["parameters"]["properties"]
    missing = [k for k in spec["parameters"]["required"] if k not in args]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}"
    unknown = [k for k in args if k not in props]
    if unknown:
        return f"unexpected argument(s): {', '.join(unknown)}"
    for k, v in args.items():
        want = props[k]["type"]
        if (want == "string" and not isinstance(v, str)) or (
            want == "integer" and (not isinstance(v, int) or isinstance(v, bool))
        ):
            return f"argument {k!r} must be a {want}"
    return None


def dispatch(ws: Workspace, name: str, args: dict[str, Any]) -> str:
    """Execute a validated tool call. Raises ToolError for recoverable failures."""
    if name == "finish":
        return "ok"
    fn = getattr(ws, name)
    return fn(**args)


def dumps(obj: Any) -> str:
    """Compact JSON that keeps non-ASCII text readable."""
    return json.dumps(obj, ensure_ascii=False)
