"""Scoring: a frontier-model judge plus deterministic tool-call and efficiency scorers.

The judge compares each attempt's diff (or plan) against the change that
actually merged. It is asked whether a reviewer would accept the attempt as
solving the task — not whether it is textually identical — so equivalent
implementations pass.

All three scorers are module-level singletons on purpose: Weave's compare view
only lines up columns whose scorers are the *same* objects across evaluations.
"""

from __future__ import annotations

import json
from typing import Any

import weave

from .agent import tool_call_accuracy

MAX_DIFF_CHARS = 60_000

JUDGE_SYSTEM = """You are a senior engineer grading attempts by a coding agent.
Each attempt is a change to a repository that was meant to implement a task. You are given the task,
the change that was actually merged by the team (the reference), and the agent's attempt.

Grade whether a reviewer on this team would accept the attempt as completing the task.
- The attempt does NOT need to match the reference line by line. A different implementation that
  achieves the same behavior, in a reasonable place, in the codebase's style, should pass.
- Missing a required part of the change, breaking existing behavior, editing unrelated code, leaving
  syntax errors, or stubbing things out is a failure or partial.
- Treat the reference as the best available evidence of what "done" means for this task.
- Judge only what is in the diff. Do not reward a confident summary that the diff does not support.

Verdicts: "pass" (would be accepted, perhaps with nits), "partial" (right direction, but a reviewer
would send it back), "fail" (wrong, broken, or not attempted)."""

PLAN_SYSTEM = """You are a senior engineer grading implementation plans written by a coding agent.
The agent explored a repository read-only and proposed a plan for a task. You are given the task,
the change that was actually merged (the reference), and the agent's plan.

Grade whether the plan would lead an engineer to an acceptable implementation:
- Does it identify the files and components that actually needed to change?
- Is the proposed approach consistent with what was merged (or an equally valid alternative)?
- Is it specific enough to act on, without inventing files, APIs, or behavior that do not exist?

Verdicts: "pass" (an engineer could implement the change from this plan), "partial" (right area,
but missing key pieces or partly wrong), "fail" (wrong files/approach, or too vague to use)."""

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "partial", "fail"]},
        "score": {"type": "number", "description": "0.0 to 1.0 overall quality"},
        "covers_reference_scope": {
            "type": "boolean",
            "description": "Changes (or plans to change) every part of the code the task needed",
        },
        "introduces_problems": {
            "type": "boolean",
            "description": "Breaks behavior, adds unrelated edits, syntax errors, or invented APIs",
        },
        "rationale": {"type": "string", "description": "Two to four sentences explaining the verdict"},
    },
    "required": ["verdict", "score", "covers_reference_scope", "introduces_problems", "rationale"],
    "additionalProperties": False,
}

# attempt_id -> judge verdict, recorded in-process for evaluate.collect_rows().
JUDGE_RESULTS: dict[str, dict[str, Any]] = {}

# Opus 5.5 list prices for judge cost accounting (USD / 1M tokens).
_JUDGE_PRICES = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00)}


def _clip(text: str, limit: int = MAX_DIFF_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n... [truncated {len(text) - limit} characters]"


def _fail(reason: str, cost_usd: float | None) -> dict[str, Any]:
    return {
        "passed": False, "score": 0.0, "verdict": "fail", "covers_reference_scope": False,
        "introduces_problems": False, "rationale": reason, "judged": False, "cost_usd": cost_usd, "judge_cost_usd": 0.0,
    }  # fmt: skip


class CompletionJudge(weave.Scorer):
    """Frontier-model grade of each attempt against the merged change.

    ``summarize`` adds the headline economics: ``cost_per_success`` is the total
    spend on all attempts divided by the number that passed.
    """

    judge_model: str = "claude-opus-5-5"
    effort: str = "medium"
    count_partial_as_pass: bool = False
    # Set judge_provider="openai" to grade with any OpenAI-compatible model instead of Claude
    # (e.g. a strong open model on Serverless Inference that is not one of the candidates).
    judge_provider: str = "anthropic"
    judge_base_url: str | None = None
    judge_api_key_env: str = "SI_API_KEY"
    judge_project: str | None = None
    judge_input_price: float = 0.0
    judge_output_price: float = 0.0

    @weave.op
    def score(
        self, *, output: dict[str, Any], prompt: str, mode: str, reference_diff: str, title: str = ""
    ) -> dict[str, Any]:
        """Grade one attempt and record the verdict for ``collect_rows``."""
        result = self._grade(output, prompt, mode, reference_diff)
        if attempt_id := output.get("attempt_id"):
            JUDGE_RESULTS[attempt_id] = result
        return result

    def _grade(self, output: dict[str, Any], prompt: str, mode: str, reference_diff: str) -> dict[str, Any]:
        cost = output.get("cost_usd")
        if output.get("error") and not output.get("diff") and not output.get("summary"):
            return _fail(f"attempt did not run: {output['error'][:300]}", cost)
        if mode == "plan":
            candidate = output.get("summary", "").strip()
            if not candidate:
                return _fail("no plan was produced", cost)
            if output.get("diff", "").strip():
                return _fail("planning task modified files", cost)
            system, label = PLAN_SYSTEM, "AGENT PLAN"
        else:
            candidate = output.get("diff", "").strip()
            if not candidate:
                return _fail(f"no changes were made (stop reason: {output.get('stop_reason')})", cost)
            system, label = JUDGE_SYSTEM, "AGENT DIFF"

        user = (
            f"<task>\n{prompt}\n</task>\n\n"
            f"<reference_merged_change>\n{_clip(reference_diff)}\n</reference_merged_change>\n\n"
            f"<{label.lower().replace(' ', '_')}>\n{_clip(candidate)}\n</{label.lower().replace(' ', '_')}>\n\n"
            f"<agent_summary>\n{_clip(output.get('summary', ''), 4000)}\n</agent_summary>"
        )
        if self.judge_provider == "openai":
            verdict, judge_cost, problem = self._ask_openai(system, user)
        else:
            verdict, judge_cost, problem = self._ask_anthropic(system, user)
        if problem:
            result = _fail(f"judge failed: {problem}", cost)
            result["judge_cost_usd"] = judge_cost
            result["judge_error"] = True  # reported separately: not the candidate's failure
            return result
        passed = verdict["verdict"] == "pass" or (self.count_partial_as_pass and verdict["verdict"] == "partial")
        return {
            **verdict,
            "score": max(0.0, min(1.0, float(verdict["score"]))),
            "passed": passed,
            "judged": True,
            "cost_usd": cost,
            "judge_cost_usd": round(judge_cost, 6),
            "judge_model": self.judge_model,
        }

    def _ask_anthropic(self, system: str, user: str) -> tuple[dict[str, Any] | None, float, str | None]:
        import anthropic

        client = anthropic.Anthropic(max_retries=4)
        resp = client.messages.create(
            model=self.judge_model,
            max_tokens=16000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": VERDICT_SCHEMA}},
        )
        inp, out = _JUDGE_PRICES.get(self.judge_model, (0.0, 0.0))
        u = resp.usage
        judge_cost = (
            (u.input_tokens + (u.cache_creation_input_tokens or 0) * 1.25) * inp
            + (u.cache_read_input_tokens or 0) * inp * 0.05
            + u.output_tokens * out
        ) / 1e6
        if resp.stop_reason in ("refusal", "max_tokens"):
            return None, judge_cost, f"stopped with {resp.stop_reason}"
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            verdict = json.loads(text)
        except json.JSONDecodeError:
            verdict = None
        if not isinstance(verdict, dict) or verdict.get("verdict") not in ("pass", "partial", "fail"):
            return None, judge_cost, f"unparseable verdict (stop_reason={resp.stop_reason})"
        return verdict, judge_cost, None

    def _ask_openai(self, system: str, user: str) -> tuple[dict[str, Any] | None, float, str | None]:
        import os

        from openai import BadRequestError, OpenAI

        from .agent import repair_json

        key = os.environ.get(self.judge_api_key_env) or os.environ.get("WANDB_API_KEY")
        headers = {"OpenAI-Project": self.judge_project} if self.judge_project else None
        client = OpenAI(base_url=self.judge_base_url, api_key=key, default_headers=headers, max_retries=4, timeout=600)
        instructions = (
            system + "\n\nRespond with only a JSON object with these keys: verdict (pass|partial|fail), "
            "score (0.0-1.0), covers_reference_scope (bool), introduces_problems (bool), rationale (string)."
        )
        messages = [{"role": "system", "content": instructions}, {"role": "user", "content": user}]
        schema_format = {
            "type": "json_schema",
            "json_schema": {"name": "verdict", "schema": VERDICT_SCHEMA, "strict": True},
        }
        try:
            resp = client.chat.completions.create(
                model=self.judge_model, messages=messages, max_tokens=16000, response_format=schema_format
            )
        except BadRequestError:  # endpoint without structured outputs: rely on the instructions
            resp = client.chat.completions.create(model=self.judge_model, messages=messages, max_tokens=16000)
        u = resp.usage
        judge_cost = (
            (u.prompt_tokens or 0) * self.judge_input_price + (u.completion_tokens or 0) * self.judge_output_price
        ) / 1e6
        choice = resp.choices[0]
        verdict = repair_json(choice.message.content or "")
        required = set(VERDICT_SCHEMA["required"])
        if not verdict or not required <= verdict.keys() or verdict.get("verdict") not in ("pass", "partial", "fail"):
            return None, judge_cost, f"unparseable verdict (finish_reason={choice.finish_reason})"
        return verdict, judge_cost, None

    @weave.op
    def summarize(self, score_rows: list) -> dict[str, Any] | None:
        """Pass rate, partial rate, total spend, and cost per successful task."""
        rows = [r for r in score_rows if isinstance(r, dict)]
        if not rows:
            return None
        n = len(rows)
        passes = sum(bool(r.get("passed")) for r in rows)
        costs = [r.get("cost_usd") for r in rows]
        known = [c for c in costs if c is not None]
        total = sum(known) if len(known) == n else None
        return {
            "pass_rate": passes / n,
            "partial_rate": sum(r.get("verdict") == "partial" for r in rows) / n,
            "mean_score": sum(float(r.get("score") or 0) for r in rows) / n,
            "attempts": n,
            "passes": passes,
            "total_cost_usd": total,
            "cost_per_success": (total / passes) if (total is not None and passes) else None,
            "judge_cost_usd": sum(float(r.get("judge_cost_usd") or 0) for r in rows),
        }


@weave.op
def tool_call_scorer(output: dict[str, Any]) -> dict[str, Any]:
    """Did the model's tool calls arrive well-formed, before any harness repair?"""
    events = output.get("events") or {}
    acc = tool_call_accuracy(events)
    return {
        "accuracy_raw": acc,
        "silent_stop": output.get("stop_reason") in ("dropped_tool_call", "leaked_tool_call"),
        "dropped": events.get("dropped", 0),
        "leaked": events.get("leaked", 0),
        "malformed_args": events.get("malformed_args", 0),
        "unknown_tool": events.get("unknown_tool", 0),
        "truncated": events.get("truncated", 0),
        "repairs": output.get("repairs", 0),
        "nudges": output.get("nudges", 0),
        "tool_errors": output.get("tool_errors", 0),
    }


@weave.op
def efficiency_scorer(output: dict[str, Any]) -> dict[str, Any]:
    """Turns, tokens, time, and cost for the attempt."""
    model_time = output.get("model_time_s") or 0.0
    out_tokens = output.get("output_tokens") or 0
    return {
        "turns": output.get("turns", 0),
        "output_tokens": out_tokens,
        "input_tokens": output.get("input_tokens", 0),
        "wall_s": output.get("wall_s"),
        "ttft_s": output.get("ttft_s"),
        "output_tokens_per_s": (out_tokens / model_time) if model_time else None,
        "cost_usd": output.get("cost_usd"),
    }


JUDGE = CompletionJudge()
SCORERS = [JUDGE, tool_call_scorer, efficiency_scorer]
