"""Tool-call survival probe: a one-minute check to run before the full eval.

Each probe is a single model turn, mid-conversation, where the only correct
response is a specific tool call. The probes target the places where serving
stacks lose tool calls in practice:

* arguments full of quotes, backslashes, tabs and non-ASCII text (escaping bugs),
* a long ``write_file`` payload (streamed-argument assembly, length limits),
* a call deep in a trajectory after several tool results (template drift),
* the final ``finish`` call (models that "just answer" instead of calling it).

Each probe runs with streaming on and off, because servers parse the two paths
with different code — a model can be clean on one and drop calls on the other.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import weave

from .agent import _LEAK_HINT, SYSTEM_PROMPT, AnthropicBackend, OpenAICompatibleBackend, make_backend
from .models import ModelSpec
from .workspace import validate_args

_TRICKY_FILE = """import re

GREETING = "Héllo, \\"world\\" — naïve café ☕"
PATTERN = re.compile(r"^\\s*(?P<key>[\\w.-]+)\\s*=\\s*'(?P<val>[^']*)'\\s*$")
\tTABBED = {"path": "C:\\\\Users\\\\dev", "emoji": "🚀"}


def render(name: str) -> str:
    return f"{GREETING} {name!r}"
"""

_SETUP = [
    ("list_files", {"path": "."}, "README.md\nsrc/strings.py\nsrc/config.py\ntests/test_strings.py"),
    (
        "read_file",
        {"path": "src/strings.py"},
        "\n".join(f"{i:>6}\t{ln}" for i, ln in enumerate(_TRICKY_FILE.splitlines(), 1)),
    ),
]


_CLAUDE_ID_TAIL = "XvGmT8bQ4kY7nLpR2sW9a"


def _history(
    backend: Any, task: str, setup: list[tuple[str, dict[str, Any], str]], id_style: str = "openai"
) -> list[dict[str, Any]]:
    """Build a mid-trajectory conversation in the backend's native message shape.

    ``id_style`` sets the tool-call ids in the replayed history: ``"openai"``
    (``call_probe0``, what most harnesses mint), ``"kimi"`` (``functions.read_file:0``,
    the format Kimi models emit themselves), or ``"claude"`` (``toolu_01…``, a history
    written by Claude and handed to an open model, as a per-request router does).
    """
    if isinstance(backend, AnthropicBackend):
        msgs: list[dict[str, Any]] = [{"role": "user", "content": task}]
        for i, (name, args, result) in enumerate(setup):
            cid = f"toolu_probe{i}"
            msgs.append(
                {"role": "assistant", "content": [{"type": "tool_use", "id": cid, "name": name, "input": args}]}
            )
            msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": cid, "content": result}]})
        return msgs
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": task}]
    for i, (name, args, result) in enumerate(setup):
        cid = {"kimi": f"functions.{name}:{i}", "claude": f"toolu_01{_CLAUDE_ID_TAIL}{i}"}.get(
            id_style, f"call_probe{i}"
        )
        msgs.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]})  # fmt: skip
        msgs.append({"role": "tool", "tool_call_id": cid, "content": result})
    return msgs


_SEARCH_RESULT = 'src/strings.py:8:def render(name: str) -> str:\ntests/test_strings.py:4:    assert render("a")'
_TEST_FILE = (
    '     1\tfrom src.strings import render\n     2\t\n     3\tdef test_render():\n     4\t    assert render("a")'
)
_RENAME_EDIT = {"path": "src/strings.py", "old_str": "def render(", "new_str": "def render_greeting("}
_DOCSTRING_EDIT = {
    "path": "src/config.py",
    "old_str": "RETRIES = 3",
    "new_str": '"""Runtime configuration."""\n\nRETRIES = 3',
}
_CONFIG_AFTER = '     1\t"""Runtime configuration."""\n     2\t\n     3\tRETRIES = 3'


def _check_edit(args: dict[str, Any]) -> str | None:
    if "naïve café" not in args.get("old_str", "") and "GREETING" not in args.get("old_str", ""):
        return "old_str does not target the GREETING line"
    if "Bonjour" not in args.get("new_str", ""):
        return "new_str does not contain the requested text"
    return None


def _check_write(args: dict[str, Any]) -> str | None:
    lines = args.get("content", "").count("\n")
    return None if lines >= 100 else f"content has only {lines} lines (expected ~150)"


PROBES: list[dict[str, Any]] = [
    {
        "name": "first_call",
        "task": "Find where the retry limit is configured in this repository and tell me its value.",
        "setup": [],
        "expect": {"list_files", "search", "read_file", "run_command"},
    },
    {
        "name": "escaped_edit",
        "task": 'In src/strings.py, change GREETING so the text reads "Bonjour, \\"monde\\" — naïve café ☕" '
        "(keep the escaped quotes). Make the edit with edit_file.",
        "setup": _SETUP,
        "expect": {"edit_file"},
        "check": _check_edit,
        "check_tool": "edit_file",
    },
    {
        "name": "long_write",
        "task": "Create tests/test_render.py containing 30 separate pytest test functions for render(), "
        "each with a docstring and three assertions. Write the whole file with one write_file call.",
        "setup": _SETUP,
        # Reading before writing is reasonable; the length check applies only to write_file.
        "expect": {"write_file", "read_file", "list_files", "search"},
        "check": _check_write,
        "check_tool": "write_file",
    },
    {
        "name": "deep_trajectory",
        "task": "Rename the function render to render_greeting everywhere it is used.",
        "setup": _SETUP
        + [
            ("search", {"pattern": "render\\("}, _SEARCH_RESULT),
            ("read_file", {"path": "tests/test_strings.py"}, _TEST_FILE),
            ("edit_file", _RENAME_EDIT, "edited src/strings.py"),
        ],
        "expect": {"edit_file", "write_file"},
    },
    {
        # Same conversation as deep_trajectory, but the replayed tool-call ids use Kimi's
        # own format. Kimi models on some serving stacks silently drop the next call when
        # history ids are OpenAI-style; this is the control for that.
        "name": "deep_trajectory_kimi_ids",
        "task": "Rename the function render to render_greeting everywhere it is used.",
        "setup": None,  # filled in below from deep_trajectory
        "id_style": "kimi",
        "expect": {"edit_file", "write_file"},
    },
    {
        # A history produced by Claude (Claude-style ids) continued by an open model: what a
        # router sending "easy" turns to an open model mid-task actually sends.
        "name": "deep_trajectory_claude_ids",
        "task": "Rename the function render to render_greeting everywhere it is used.",
        "setup": None,  # filled in below from deep_trajectory
        "id_style": "claude",
        "expect": {"edit_file", "write_file"},
    },
    {
        "name": "finish_call",
        "task": "Add a module docstring to src/config.py.",
        "setup": [
            ("read_file", {"path": "src/config.py"}, "     1\tRETRIES = 3"),
            ("edit_file", _DOCSTRING_EDIT, "edited src/config.py"),
            ("read_file", {"path": "src/config.py"}, _CONFIG_AFTER),
        ],
        "expect": {"finish"},
    },
]  # fmt: skip
_deep = next(p for p in PROBES if p["name"] == "deep_trajectory")
for _variant in ("deep_trajectory_kimi_ids", "deep_trajectory_claude_ids"):
    next(p for p in PROBES if p["name"] == _variant)["setup"] = _deep["setup"]


def _classify(turn: Any, probe: dict[str, Any]) -> tuple[str, str | None]:
    if turn.finish_reason == "length" and not turn.tool_calls:
        return "truncated", None
    if not turn.tool_calls:
        if turn.text and _LEAK_HINT.search(turn.text):
            return "leaked", turn.text[:300]
        return "dropped", (turn.text or "")[:300] or f"finish_reason={turn.finish_reason}, empty response"
    call = turn.tool_calls[0]
    if call.problem:
        return "malformed_args", call.problem
    if err := validate_args(call.name, call.args):
        return ("unknown_tool" if "unknown tool" in err else "malformed_args"), err
    if call.name not in probe["expect"]:
        return "wrong_tool", f"called {call.name}, expected one of {sorted(probe['expect'])}"
    check = probe.get("check")
    if check and call.name == probe.get("check_tool", call.name) and (err := check(call.args)):
        return "bad_content", err
    return "ok", None


def _run_one(spec: ModelSpec, probe: dict[str, Any], stream: bool, trial: int) -> dict[str, Any]:
    backend = make_backend(spec, stream=stream)
    base = {"model": spec.label, "probe": probe["name"], "stream": stream, "trial": trial}
    if isinstance(backend, AnthropicBackend) and not stream:
        return {**base, "result": "skipped", "detail": "Claude backend always streams"}
    try:
        turn = backend.complete(_history(backend, probe["task"], probe["setup"], probe.get("id_style", "openai")))
    except Exception as e:  # noqa: BLE001
        return {**base, "result": "api_error", "detail": f"{type(e).__name__}: {e}"[:300]}
    result, detail = _classify(turn, probe)
    return {
        **base, "result": result, "detail": detail, "finish_reason": turn.finish_reason,
        "latency_s": round(turn.latency_s, 2), "output_tokens": turn.output_tokens,
    }  # fmt: skip


def run_probe(
    specs: list[ModelSpec], trials: int = 3, streams: tuple[bool, ...] = (True, False), parallelism: int = 8
) -> list[dict[str, Any]]:
    """Run every probe ``trials`` times per model and streaming mode. Returns one row per request."""
    jobs = [(s, p, st, t) for s in specs for p in PROBES for st in streams for t in range(trials)]
    with ThreadPoolExecutor(max_workers=parallelism) as pool:
        rows = list(pool.map(lambda j: _run_one(*j), jobs))
    return [r for r in rows if r["result"] != "skipped"]


_SUMMARY_COUNTS = ("dropped", "leaked", "malformed_args", "truncated", "wrong_tool", "bad_content", "api_error")


def summarize_probe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per (model, streaming) survival rate and failure breakdown."""
    groups: dict[tuple[str, bool], list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r["model"], r["stream"]), []).append(r)
    out = []
    for (model, stream), rs in sorted(groups.items()):
        n = len(rs)
        counts: dict[str, int] = {}
        for r in rs:
            counts[r["result"]] = counts.get(r["result"], 0) + 1
        answered = n - counts.get("api_error", 0)  # an HTTP error says nothing about tool-call format
        format_ok = answered - sum(
            counts.get(k, 0) for k in ("leaked", "dropped", "malformed_args", "unknown_tool", "truncated")
        )
        out.append(
            {
                "model": model,
                "stream": stream,
                "requests": n,
                "tool_call_survival": round(format_ok / answered, 3) if answered else None,
                "fully_correct": round(counts.get("ok", 0) / answered, 3) if answered else None,
                **{k: counts.get(k, 0) for k in _SUMMARY_COUNTS},
            }
        )
    return out


# --------------------------------------------------------------------------
# The probe as a Weave evaluation: one row per (probe, streaming mode)
# --------------------------------------------------------------------------

PROBE_FAILURES = ("dropped", "leaked", "malformed_args", "unknown_tool", "truncated")


def probe_rows() -> list[dict[str, Any]]:
    """Dataset rows for the Weave probe evaluation."""
    return [
        {"case": f"{p['name']} · {'stream' if st else 'no-stream'}", "probe": p["name"], "stream": st,
         "task": p["task"], "id_style": p.get("id_style", "openai"), "history_tool_calls": len(p["setup"])}
        for p in PROBES
        for st in (True, False)
    ]  # fmt: skip


class ProbeModel(weave.Model):
    """One model endpoint answering single probe turns."""

    label: str
    spec: dict[str, Any]

    @weave.op
    def predict(self, probe: str, stream: bool) -> dict[str, Any]:
        """Send the probe's conversation and classify the reply."""
        spec = ModelSpec(**self.spec)
        p = next(x for x in PROBES if x["name"] == probe)
        backend = make_backend(spec, stream=stream)
        try:
            turn = backend.complete(_history(backend, p["task"], p["setup"], p.get("id_style", "openai")))
        except Exception as e:  # noqa: BLE001
            return {"result": "api_error", "detail": f"{type(e).__name__}: {e}"[:500]}
        result, detail = _classify(turn, p)
        return {
            "result": result,
            "detail": detail,
            "finish_reason": turn.finish_reason,
            "tool_calls": [{"name": c.name, "arguments": c.raw_args} for c in turn.tool_calls],
            "text": turn.text[:2000],
            "output_tokens": turn.output_tokens,
            "latency_s": round(turn.latency_s, 3),
        }


@weave.op
def tool_call_survival(output: dict[str, Any]) -> dict[str, Any]:
    """Did the tool call arrive as a tool call? Format failures vs. reasoning misses."""
    result = output.get("result")
    answered = result != "api_error"
    return {
        "survived": answered and result not in PROBE_FAILURES,
        "fully_correct": result == "ok",
        "silent_drop": result == "dropped",
        "leaked_as_text": result == "leaked",
        "malformed": result in ("malformed_args", "unknown_tool"),
        "api_error": not answered,
    }


def run_probe_weave(
    specs: list[ModelSpec], project: str, trials: int = 3, suite_name: str = "tool-call-probe"
) -> dict[str, Any]:
    """Log the probe to Weave: one shared dataset, one evaluation per model. Returns the compare link."""
    import asyncio
    import threading
    import urllib.parse

    client = weave.init(project)
    dataset = weave.Dataset(name=f"{suite_name}-cases", rows=probe_rows())
    weave.publish(dataset)
    call_ids, summaries = [], {}
    for spec in specs:
        ev = weave.Evaluation(
            name=f"{suite_name}-eval", dataset=dataset, scorers=[tool_call_survival], trials=trials,
            evaluation_name=f"{spec.label} · tool-call probe",
        )  # fmt: skip
        model = ProbeModel(name=f"probe-{spec.label}", label=spec.label, spec=spec.to_dict())
        box: dict[str, Any] = {}

        def _target(ev: weave.Evaluation = ev, model: ProbeModel = model, box: dict[str, Any] = box) -> None:
            loop = asyncio.new_event_loop()
            try:
                box["v"] = loop.run_until_complete(ev.evaluate.call(ev, model))
            finally:
                loop.close()

        th = threading.Thread(target=_target)
        th.start()
        th.join()
        summary, call = box["v"]
        summaries[spec.label] = summary
        call_ids.append(call.id)
    entity, proj = project.split("/", 1) if "/" in project else (client.entity, project)
    ids = urllib.parse.quote(json.dumps(call_ids, separators=(",", ":")))
    return {
        "summaries": summaries,
        "call_ids": call_ids,
        "compare_url": f"https://wandb.ai/{entity}/{proj}/weave/compare-evaluations?evaluationCallIds={ids}",
        "project_url": f"https://wandb.ai/{entity}/{proj}/weave/evaluations",
    }


__all__ = ["PROBES", "run_probe", "summarize_probe", "OpenAICompatibleBackend"]
