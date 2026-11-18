"""A small, instrumented coding-agent harness.

This is deliberately *not* a production coding tool. It is a minimal agent loop
with six tools (list/read/search/edit/write/run) whose job is to measure one
thing production harnesses usually hide: **whether the model's tool calls
survive the trip through your serving stack**.

Every assistant turn is classified:

``ok``             a structured tool call with valid JSON arguments for a known tool
``malformed_args`` a structured call whose arguments are not valid JSON / fail the schema
``unknown_tool``   a structured call naming a tool that does not exist
``leaked``         no structured call, but tool-call markup in the text
                   (``<tool_call>``, ``<|tool_call_begin|>``, bare ``{"name": ..}``) —
                   the serving stack's tool parser did not recognize the model's format
``dropped``        no tool call and no markup, yet the agent had not called ``finish``
                   (includes ``finish_reason == "tool_calls"`` with an empty list).
                   The agent simply stops — a *silent* failure
``truncated``      the turn hit ``max_tokens`` mid-generation

Two harness profiles show how much a harness can paper over:

``strict``     returns errors for malformed calls but does nothing else; a leaked or
               dropped call ends the run, exactly as it would in a naive client
``forgiving``  repairs malformed JSON, parses leaked tool calls out of the text, and
               nudges the model to continue after a silent stop (bounded)

Raw tool-call accuracy (before any repair) measures the model + serving stack;
the completion rate under each profile measures what your developers would see.
"""

from __future__ import annotations

import ast
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import weave

from .models import ModelSpec
from .workspace import MUTATING_TOOLS, TOOL_NAMES, TOOL_SPECS, ToolError, Workspace, dispatch, validate_args

HarnessProfile = Literal["strict", "forgiving"]
EVENT_KINDS = ("ok", "malformed_args", "unknown_tool", "leaked", "dropped", "truncated")

SYSTEM_PROMPT = """You are an autonomous software engineering agent working inside a git repository.
Use the provided tools to explore the code and make changes. Work step by step:
locate the relevant code, read it, then make focused edits that match the existing style.
Always act through tool calls; do not describe edits in prose instead of making them.
You cannot run Python, tests, or builds in this environment: `run_command` only allows read-only
commands (ls, cat, grep, find, read-only git, ...) without pipes or redirects. Reason about correctness
from the code instead of trying to execute it.
When you are done, call the `finish` tool exactly once with a short summary."""

NUDGE = (
    "You stopped without calling a tool. The task is not marked complete. "
    "Continue working by calling a tool, or call `finish` if you are done."
)


# --------------------------------------------------------------------------
# Tool-call parsing: structured, leaked, and repaired
# --------------------------------------------------------------------------

_LEAK_HINT = re.compile(
    r"<tool_call>|</tool_call>|<\|tool_call|tool▁call|<function=|<invoke |\bto=functions\.|"
    r"\"(?:name|function)\"\s*:\s*\"(?:" + "|".join(sorted(TOOL_NAMES)) + r")\"",
)
_HERMES = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_GLM = re.compile(r"<tool_call>\s*([A-Za-z_][\w]*)\s*(.*?)</tool_call>", re.DOTALL)
_GLM_ARG = re.compile(r"<arg_key>\s*(.*?)\s*</arg_key>\s*<arg_value>(.*?)</arg_value>", re.DOTALL)
_KIMI = re.compile(
    r"<\|tool_call_begin\|>\s*(?:functions\.)?([\w]+)(?::\d+)?\s*<\|tool_call_argument_begin\|>\s*(.*?)\s*<\|tool_call_end\|>",
    re.DOTALL,
)
_DEEPSEEK = re.compile(
    r"tool▁sep｜>\s*([\w]+)\s*(?:```(?:json)?)?\s*(\{.*?\})\s*(?:```)?\s*<｜tool▁call▁end", re.DOTALL
)
_HARMONY = re.compile(r"to=functions\.([\w]+).*?<\|message\|>\s*(\{.*?\})\s*(?:<\|call\|>|$)", re.DOTALL)


def repair_json(text: Any) -> dict[str, Any] | None:
    """Best-effort repair of model-produced tool arguments. Returns None if hopeless."""
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        return None
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    if (start := s.find("{")) > 0:
        s = s[start:]
    if (end := s.rfind("}")) != -1:
        s = s[: end + 1]
    for candidate in (s, re.sub(r",\s*([}\]])", r"\1", s)):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, str):  # double-encoded
                obj = json.loads(obj)
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, TypeError):
            pass
    try:  # Python-literal dicts: single quotes, True/False/None
        obj = ast.literal_eval(s)
        return obj if isinstance(obj, dict) else None
    except (ValueError, SyntaxError):
        return None


def _coerce_json_value(v: str) -> Any:
    try:
        return json.loads(v)
    except (json.JSONDecodeError, TypeError):
        return v


def parse_leaked_calls(text: str) -> list[tuple[str, dict[str, Any] | None]]:
    """Extract tool calls a model wrote as text in common open-model formats."""
    calls: list[tuple[str, dict[str, Any] | None]] = []
    for m in _HERMES.finditer(text):
        obj = repair_json(m.group(1))
        if obj and isinstance(obj.get("name"), str):
            args = obj.get("arguments", obj.get("parameters", {}))
            calls.append((obj["name"], repair_json(args) if isinstance(args, str) else args))
    if not calls:
        for m in _GLM.finditer(text):
            if m.group(1) in TOOL_NAMES:
                pairs = _GLM_ARG.findall(m.group(2))
                args = {k: _coerce_json_value(v) if k in ("start_line", "end_line") else v for k, v in pairs}
                calls.append((m.group(1), args if pairs else repair_json(m.group(2))))
    for rx in (_KIMI, _DEEPSEEK, _HARMONY):
        if not calls:
            calls = [(m.group(1), repair_json(m.group(2))) for m in rx.finditer(text)]
    if not calls:  # a bare JSON object naming a known tool
        obj = repair_json(text)
        if obj and obj.get("name") in TOOL_NAMES:
            args = obj.get("arguments", obj.get("parameters", {}))
            calls.append((obj["name"], repair_json(args) if isinstance(args, str) else args))
    return calls


# --------------------------------------------------------------------------
# Provider adapters: one normalized "turn" shape for OpenAI-compatible + Anthropic
# --------------------------------------------------------------------------


@dataclass
class ToolCall:
    """One tool call from a model turn, with its parsed arguments or the parse problem."""

    id: str
    name: str
    raw_args: Any  # str for OpenAI-compatible, dict for Anthropic
    args: dict[str, Any] | None = None
    problem: str | None = None  # parse / schema error, if any


@dataclass
class Turn:
    """A model turn normalized across providers."""

    text: str
    tool_calls: list[ToolCall]
    finish_reason: str | None
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    ttft_s: float | None = None
    raw_assistant: Any = None  # provider-native assistant message to append to history


def _openai_tools() -> list[dict[str, Any]]:
    return [{"type": "function", "function": t} for t in TOOL_SPECS]


def _anthropic_tools() -> list[dict[str, Any]]:
    return [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in TOOL_SPECS]


class OpenAICompatibleBackend:
    """Any OpenAI-compatible Chat Completions endpoint (SI, Dedicated Inference, vLLM, OpenRouter)."""

    def __init__(self, spec: ModelSpec, stream: bool = True, timeout_s: float = 300.0) -> None:
        """Create a client for ``spec``; retries are delegated to the OpenAI SDK."""
        from openai import OpenAI

        if not spec.base_url:
            raise ValueError(f"{spec.label}: base_url is required for OpenAI-compatible providers")
        headers = {"OpenAI-Project": spec.project} if spec.project else None
        self.client = OpenAI(
            base_url=spec.base_url, api_key=spec.api_key() or "missing", default_headers=headers,
            timeout=timeout_s, max_retries=3,
        )  # fmt: skip
        self.spec = spec
        self.stream = stream

    def initial_messages(self, prompt: str) -> list[dict[str, Any]]:
        """System prompt plus the task prompt."""
        return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]

    def complete(self, messages: list[dict[str, Any]]) -> Turn:  # noqa: C901
        """Send one Chat Completions request and normalize the response (streamed or not)."""
        kwargs: dict[str, Any] = {
            "model": self.spec.model,
            "messages": messages,
            "tools": _openai_tools(),
            "tool_choice": "auto",
            "max_tokens": self.spec.max_output_tokens,
            "extra_body": self.spec.extra_body or None,
        }
        t0 = time.monotonic()
        if not self.stream:
            resp = self.client.chat.completions.create(**kwargs)
            choice = resp.choices[0]
            text = choice.message.content or ""
            raw_calls = [
                {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                for tc in choice.message.tool_calls or []
            ]
            finish, usage, ttft = choice.finish_reason, resp.usage, None
        else:
            text_parts: list[str] = []
            acc: dict[int, dict[str, Any]] = {}
            finish, usage, ttft = None, None, None
            for chunk in self.client.chat.completions.create(
                **kwargs, stream=True, stream_options={"include_usage": True}
            ):
                if chunk.usage:
                    usage = chunk.usage
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if ttft is None and (delta.content or delta.tool_calls or getattr(delta, "reasoning_content", None)):
                    ttft = time.monotonic() - t0
                if delta.content:
                    text_parts.append(delta.content)
                for tc in delta.tool_calls or []:
                    slot = acc.setdefault(tc.index, {"id": None, "name": "", "arguments": ""})
                    slot["id"] = tc.id or slot["id"]
                    if tc.function and tc.function.name:
                        slot["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["arguments"] += tc.function.arguments
                if choice.finish_reason:
                    finish = choice.finish_reason
            text = "".join(text_parts)
            raw_calls = [acc[i] for i in sorted(acc)]
        latency = time.monotonic() - t0

        calls = []
        for rc in raw_calls:
            call_id = rc["id"] or f"call_{uuid.uuid4().hex[:12]}"
            try:
                args = json.loads(rc["arguments"]) if rc["arguments"] else {}
                problem = None if isinstance(args, dict) else "arguments are not a JSON object"
                args = args if isinstance(args, dict) else None
            except json.JSONDecodeError as e:
                args, problem = None, f"invalid JSON arguments: {e}"
            calls.append(ToolCall(id=call_id, name=rc["name"], raw_args=rc["arguments"], args=args, problem=problem))

        raw_assistant: dict[str, Any] = {"role": "assistant", "content": text or None}
        if calls:
            raw_assistant["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.raw_args or "{}"}}
                for c in calls
            ]
        cached = 0
        if usage is not None and getattr(usage, "prompt_tokens_details", None):
            cached = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0
        return Turn(
            text=text,
            tool_calls=calls,
            finish_reason=finish,
            input_tokens=(usage.prompt_tokens if usage else 0) or 0,
            cached_input_tokens=cached,
            output_tokens=(usage.completion_tokens if usage else 0) or 0,
            latency_s=latency,
            ttft_s=ttft,
            raw_assistant=raw_assistant,
        )

    def append_turn(self, messages: list[dict[str, Any]], turn: Turn, results: list[tuple[str, str]]) -> None:
        """Append the assistant turn and one ``tool`` message per call."""
        messages.append(turn.raw_assistant)
        for call_id, content in results:
            messages.append({"role": "tool", "tool_call_id": call_id, "content": content})

    def append_user(self, messages: list[dict[str, Any]], turn: Turn, text: str) -> None:
        """Append the assistant turn and a plain user message (used for nudges)."""
        messages.append(
            turn.raw_assistant if turn.raw_assistant.get("content") else {"role": "assistant", "content": ""}
        )
        messages.append({"role": "user", "content": text})


class AnthropicBackend:
    """Claude via the Anthropic SDK (closed-model baseline).

    Server-side refusal fallbacks are intentionally NOT enabled: in an
    evaluation, silently serving a turn from a different model would corrupt
    the measurement. Refusals are recorded as their own stop reason instead.
    """

    def __init__(self, spec: ModelSpec, timeout_s: float = 600.0) -> None:
        """Create an Anthropic client for ``spec``."""
        import anthropic

        self.client = anthropic.Anthropic(api_key=spec.api_key(), timeout=timeout_s, max_retries=3)
        self.spec = spec

    def initial_messages(self, prompt: str) -> list[dict[str, Any]]:
        """The task prompt as the first user message (the system prompt is sent separately)."""
        return [{"role": "user", "content": prompt}]

    def complete(self, messages: list[dict[str, Any]]) -> Turn:
        """Send one Messages request (streamed) and normalize the response."""
        kwargs: dict[str, Any] = {
            "model": self.spec.model,
            "max_tokens": self.spec.max_output_tokens,
            "system": SYSTEM_PROMPT,
            "tools": _anthropic_tools(),
            "messages": messages,
            "cache_control": {"type": "ephemeral"},  # agent loops resend the prefix every turn
        }
        if effort := (self.spec.extra_body or {}).get("effort"):
            kwargs["output_config"] = {"effort": effort}
        t0 = time.monotonic()
        ttft = None
        with self.client.messages.stream(**kwargs) as stream:
            for _event in stream:
                if ttft is None:
                    ttft = time.monotonic() - t0
            msg = stream.get_final_message()
        latency = time.monotonic() - t0
        text = "".join(b.text for b in msg.content if b.type == "text")
        calls = []
        for b in msg.content:
            if b.type == "tool_use":
                ok = isinstance(b.input, dict)
                calls.append(
                    ToolCall(
                        id=b.id, name=b.name, raw_args=b.input,
                        args=b.input if ok else None, problem=None if ok else "input is not an object",
                    )
                )  # fmt: skip
        u = msg.usage
        cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0
        return Turn(
            text=text,
            tool_calls=calls,
            finish_reason=msg.stop_reason,
            input_tokens=(u.input_tokens or 0) + cache_read + cache_write,
            cached_input_tokens=cache_read,
            cache_write_tokens=cache_write,
            output_tokens=u.output_tokens or 0,
            latency_s=latency,
            ttft_s=ttft,
            raw_assistant={"role": "assistant", "content": msg.content},  # keeps thinking blocks intact
        )

    def append_turn(self, messages: list[dict[str, Any]], turn: Turn, results: list[tuple[str, str]]) -> None:
        """Append the assistant content blocks and all tool results in one user message."""
        messages.append(turn.raw_assistant)
        messages.append(
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": cid, "content": c} for cid, c in results],
            }
        )

    def append_user(self, messages: list[dict[str, Any]], turn: Turn, text: str) -> None:
        """Append the assistant turn and a plain user message (used for nudges)."""
        messages.append(turn.raw_assistant)
        messages.append({"role": "user", "content": text})


def make_backend(spec: ModelSpec, stream: bool = True) -> OpenAICompatibleBackend | AnthropicBackend:
    """Return the backend for ``spec.provider``."""
    if spec.provider == "anthropic":
        return AnthropicBackend(spec)
    return OpenAICompatibleBackend(spec, stream=stream)


# --------------------------------------------------------------------------
# The agent loop
# --------------------------------------------------------------------------


@dataclass
class RunConfig:
    """Limits and harness behavior for one attempt."""

    profile: HarnessProfile = "strict"
    max_turns: int = 50
    max_wall_s: float = 900.0
    max_nudges: int = 2
    stream: bool = True
    allow_any_command: bool = False
    keep_transcript_turns: int = 60


@dataclass
class Trajectory:
    """Everything recorded about one attempt: outcome, tool-call events, tokens, cost, timing."""

    finished: bool = False
    stop_reason: str = "max_turns"
    summary: str = ""
    turns: int = 0
    events: dict[str, int] = field(default_factory=lambda: dict.fromkeys(EVENT_KINDS, 0))
    repairs: int = 0
    nudges: int = 0
    tool_errors: int = 0
    tool_calls_executed: int = 0
    edits: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = 0.0
    model_time_s: float = 0.0
    ttfts: list[float] = field(default_factory=list)
    error: str | None = None
    transcript: list[dict[str, Any]] = field(default_factory=list)


def _summarize_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    # Keep traces small: log only the newest message, not the whole growing history.
    msgs = inputs.get("messages") or []
    return {"turn": inputs.get("turn"), "n_messages": len(msgs), "last_message": msgs[-1] if msgs else None}


def _drop_turn_object(output: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in output.items() if k != "_turn"}


@weave.op(postprocess_inputs=_summarize_inputs, postprocess_output=_drop_turn_object)
def model_turn(backend: Any, messages: list[dict[str, Any]], turn: int) -> dict[str, Any]:
    """One model call. Traced in Weave so every tool call is inspectable."""
    t = backend.complete(messages)
    return {
        "text": t.text,
        "finish_reason": t.finish_reason,
        "tool_calls": [{"name": c.name, "arguments": c.raw_args, "problem": c.problem} for c in t.tool_calls],
        "usage": {"input": t.input_tokens, "cached": t.cached_input_tokens, "output": t.output_tokens},
        "latency_s": round(t.latency_s, 3),
        "ttft_s": None if t.ttft_s is None else round(t.ttft_s, 3),
        "_turn": t,
    }


def _postprocess_tool(output: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in output.items() if k != "content"} | {"content_preview": output.get("content", "")[:500]}


def _tool_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"name": inputs.get("name"), "args": _short(inputs.get("args"))}


@weave.op(postprocess_inputs=_tool_inputs, postprocess_output=_postprocess_tool)
def execute_tool(ws: Workspace, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Run one validated tool call. Traced in Weave; failures go back to the model as text."""
    try:
        return {"ok": True, "content": dispatch(ws, name, args)}
    except ToolError as e:
        return {"ok": False, "content": f"Error: {e}"}
    except Exception as e:  # noqa: BLE001 - surface any tool crash to the model
        return {"ok": False, "content": f"Error: {type(e).__name__}: {e}"}


def _account(traj: Trajectory, spec: ModelSpec, t: Turn) -> None:
    traj.input_tokens += t.input_tokens
    traj.cached_input_tokens += t.cached_input_tokens
    traj.output_tokens += t.output_tokens
    traj.model_time_s += t.latency_s
    if t.ttft_s is not None:
        traj.ttfts.append(t.ttft_s)
    turn_cost = spec.cost(t.input_tokens - t.cache_write_tokens, t.output_tokens, t.cached_input_tokens)
    if turn_cost is None or traj.cost_usd is None:
        traj.cost_usd = None
    else:
        write_cost = t.cache_write_tokens * (spec.input_price or 0) * 1.25 / 1e6
        traj.cost_usd += turn_cost + write_cost


def run_agent(  # noqa: C901, PLR0912, PLR0915
    spec: ModelSpec, prompt: str, ws: Workspace, cfg: RunConfig | None = None
) -> Trajectory:
    """Run one attempt of one task. Never raises for model/tool failures; they land in the Trajectory."""
    cfg = cfg or RunConfig()
    traj = Trajectory()
    backend = make_backend(spec, stream=cfg.stream)
    messages = backend.initial_messages(prompt)
    started = time.monotonic()

    while traj.turns < cfg.max_turns:
        if time.monotonic() - started > cfg.max_wall_s:
            traj.stop_reason = "timeout"
            break
        try:
            out = model_turn(backend, messages, traj.turns)
        except Exception as e:  # noqa: BLE001 - API errors end the attempt, they don't crash the eval
            traj.stop_reason, traj.error = "api_error", f"{type(e).__name__}: {e}"[:2000]
            break
        t: Turn = out["_turn"]
        traj.turns += 1
        _account(traj, spec, t)
        record: dict[str, Any] = {"turn": traj.turns, "finish_reason": t.finish_reason, "text": t.text[:800]}

        if t.finish_reason == "refusal":
            traj.stop_reason = "refusal"
            traj.transcript.append(record)
            break

        calls = t.tool_calls
        leaked_calls: list[tuple[str, dict[str, Any] | None]] = []
        if not calls:
            if t.finish_reason == "length":
                kind = "truncated"
            elif t.text and _LEAK_HINT.search(t.text):
                kind = "leaked"
                leaked_calls = parse_leaked_calls(t.text)
            else:
                kind = "dropped"
            traj.events[kind] += 1
            record["event"] = kind

            # Leak repair rewrites history as structured calls, which only the
            # OpenAI message shape allows; Claude never leaks in practice.
            if kind == "leaked" and cfg.profile == "forgiving" and leaked_calls and spec.provider == "openai":
                # Re-issue the parsed calls as if they had been structured.
                traj.repairs += 1
                calls = [
                    ToolCall(id=f"call_{uuid.uuid4().hex[:12]}", name=n, raw_args=a, args=a,
                             problem=None if isinstance(a, dict) else "unparseable arguments")
                    for n, a in leaked_calls
                ]  # fmt: skip
                # Rewrite the assistant turn so the history carries real tool calls.
                t.raw_assistant = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.args or {})},
                        }
                        for c in calls
                    ],
                }
                t.tool_calls = calls
            elif cfg.profile == "forgiving" and traj.nudges < cfg.max_nudges:
                traj.nudges += 1
                backend.append_user(messages, t, NUDGE)
                traj.transcript.append(record)
                continue
            else:
                traj.stop_reason = {"truncated": "truncated", "leaked": "leaked_tool_call"}.get(
                    kind, "dropped_tool_call"
                )
                traj.transcript.append(record)
                break

        results: list[tuple[str, str]] = []
        finished = False
        record["calls"] = []
        for c in calls:
            if c.args is None and cfg.profile == "forgiving" and (fixed := repair_json(c.raw_args)) is not None:
                c.args, c.problem = fixed, None
                traj.repairs += 1
            problem = c.problem or validate_args(c.name, c.args)
            if not leaked_calls:  # leaked turns were already counted above
                kind = "unknown_tool" if c.name not in TOOL_NAMES else ("malformed_args" if c.problem else "ok")
                if kind == "ok" and problem:
                    kind = "malformed_args"
                traj.events[kind] += 1
            if problem:
                results.append((c.id, f"Error: {problem}. Call the tool again with valid arguments."))
                record["calls"].append({"name": c.name, "error": problem})
                continue
            res = execute_tool(ws, c.name, c.args)
            traj.tool_calls_executed += 1
            if not res["ok"]:
                traj.tool_errors += 1
            elif c.name in MUTATING_TOOLS:
                traj.edits += 1
            results.append((c.id, res["content"]))
            record["calls"].append({"name": c.name, "args": _short(c.args), "ok": res["ok"]})
            if c.name == "finish":
                finished = True
                traj.summary = c.args.get("summary", "")
        backend.append_turn(messages, t, results)
        if len(traj.transcript) < cfg.keep_transcript_turns:
            traj.transcript.append(record)
        if finished:
            traj.finished, traj.stop_reason = True, "finished"
            break

    return traj


def _short(args: dict[str, Any] | None, limit: int = 200) -> dict[str, Any]:
    return {k: (v[:limit] + "…" if isinstance(v, str) and len(v) > limit else v) for k, v in (args or {}).items()}


def tool_call_accuracy(events: dict[str, int]) -> float | None:
    """Share of tool-call attempts that arrived well-formed, before any harness repair.

    Each structured call counts once; a turn that leaked, dropped, or truncated
    its call counts once as a failed attempt.
    """
    total = sum(events.values())
    return None if total == 0 else events.get("ok", 0) / total
