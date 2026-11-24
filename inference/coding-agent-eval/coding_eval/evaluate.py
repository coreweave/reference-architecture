"""Run the evaluation in Weave: one shared dataset, one Evaluation per model.

Weave's compare view only works when every model is evaluated on the *same*
dataset object with the *same* scorer objects, and its column headers come from
``evaluation_name`` (not ``name``). This module enforces all three.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import urllib.parse
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import weave

from .agent import RunConfig, run_agent
from .grading import JUDGE_RESULTS, CompletionJudge, efficiency_scorer, tool_call_scorer
from .models import ModelSpec
from .tasks import DEFAULT_CACHE_DIR, prepare_repo, repo_cache_dir
from .workspace import Workspace

# Every attempt and its judge verdict, recorded in-process (Weave runs predict and
# scorers in worker threads of this process). collect_rows() joins them for analysis
# in the notebook without having to query Weave back.
ATTEMPTS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def _record(output: dict[str, Any], suite: str, category: str | None) -> dict[str, Any]:
    output["attempt_id"] = uuid.uuid4().hex
    with _LOCK:
        ATTEMPTS[output["attempt_id"]] = {**output, "suite": suite, "category": category}
    return output


class CodingAgentModel(weave.Model):
    """A model endpoint + harness profile, evaluated as a Weave Model."""

    label: str
    spec: dict[str, Any]
    profile: str = "strict"
    max_turns: int = 50
    max_wall_s: float = 900.0
    stream: bool = True
    allow_any_command: bool = False
    suite: str = ""

    @weave.op
    def predict(  # noqa: PLR0913
        self, task_id: str, prompt: str, repo: str, base_sha: str, mode: str = "edit", category: str | None = None
    ) -> dict[str, Any]:
        """Run one attempt of one task in a fresh workspace and return its full record."""
        spec = ModelSpec(**self.spec)
        cfg = RunConfig(
            profile=self.profile,  # type: ignore[arg-type]
            max_turns=self.max_turns,
            max_wall_s=self.max_wall_s,
            stream=self.stream,
            allow_any_command=self.allow_any_command,
        )
        started = time.monotonic()
        ws = None
        try:
            ws = Workspace.create(
                repo_cache_dir(repo, DEFAULT_CACHE_DIR), base_sha,
                read_only=(mode == "plan"), allow_any_command=self.allow_any_command,
            )  # fmt: skip
            traj = run_agent(spec, prompt, ws, cfg)
            diff = ws.diff()
        except Exception as e:  # noqa: BLE001 - setup failures become a failed attempt, not a crashed eval
            failed = {
                "task_id": task_id,
                "model": self.label,
                "profile": self.profile,
                "mode": mode,
                "error": f"{type(e).__name__}: {e}",
                "diff": "",
                "summary": "",
                "stop_reason": "setup_error",
                "events": {},
                "cost_usd": 0.0,
                "wall_s": time.monotonic() - started,
            }
            return _record(failed, self.suite, category)
        finally:
            if ws is not None:
                ws.cleanup()
        return _record(
            {
                "task_id": task_id,
                "model": self.label,
                "profile": self.profile,
                "mode": mode,
                "finished": traj.finished,
                "stop_reason": traj.stop_reason,
                "summary": traj.summary,
                "diff": diff,
                "diff_lines": sum(1 for ln in diff.splitlines() if ln[:1] in "+-" and ln[:3] not in ("+++", "---")),
                "turns": traj.turns,
                "events": traj.events,
                "repairs": traj.repairs,
                "nudges": traj.nudges,
                "tool_errors": traj.tool_errors,
                "tool_calls_executed": traj.tool_calls_executed,
                "edits": traj.edits,
                "input_tokens": traj.input_tokens,
                "cached_input_tokens": traj.cached_input_tokens,
                "output_tokens": traj.output_tokens,
                "cost_usd": traj.cost_usd,
                "model_time_s": traj.model_time_s,
                "ttft_s": (sum(traj.ttfts) / len(traj.ttfts)) if traj.ttfts else None,
                "wall_s": time.monotonic() - started,
                "error": traj.error,
                "transcript": traj.transcript,
            },
            self.suite,
            category,
        )


def _run_coroutine(coro: Any) -> Any:
    """Run a coroutine from sync code even if this thread already has a running loop (marimo)."""
    box: dict[str, Any] = {}

    def target() -> None:
        loop = asyncio.new_event_loop()
        try:
            box["value"] = loop.run_until_complete(coro)
        except BaseException as e:  # noqa: BLE001
            box["error"] = e
        finally:
            loop.close()

    th = threading.Thread(target=target, daemon=True)
    th.start()
    th.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


def compare_url(entity: str, project: str, call_ids: list[str]) -> str | None:
    """Build a Weave compare-evaluations link for two or more evaluation call ids."""
    if len(call_ids) < 2:
        return None
    ids = urllib.parse.quote(json.dumps(call_ids, separators=(",", ":")))
    return f"https://wandb.ai/{entity}/{project}/weave/compare-evaluations?evaluationCallIds={ids}"


def estimate_requests(n_tasks: int, n_models: int, trials: int, mean_turns: float = 15.0) -> dict[str, float]:
    """Rough request counts for a planned run, shown before the user starts it."""
    attempts = n_tasks * n_models * trials
    return {"attempts": attempts, "model_requests": attempts * mean_turns, "judge_requests": attempts}


def run_suite(  # noqa: PLR0913
    tasks: list[dict[str, Any]],
    specs: list[ModelSpec],
    *,
    project: str,
    suite_name: str = "coding-agent-eval",
    trials: int = 3,
    profile: str = "strict",
    judge: CompletionJudge | None = None,
    parallelism: int = 8,
    max_turns: int = 50,
    max_wall_s: float = 900.0,
    stream: bool = True,
    allow_any_command: bool = False,
    on_model_done: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Evaluate every model in ``specs`` on ``tasks`` and return summaries + a compare link.

    ``project`` is ``"entity/project"`` in W&B. Each model runs ``trials``
    attempts per task, ``parallelism`` attempts at a time; all models run
    concurrently, so up to ``parallelism * len(specs)`` attempts are in flight.
    """
    os.environ["WEAVE_PARALLELISM"] = str(parallelism)
    client = weave.init(project)
    for repo in {t["repo"] for t in tasks}:
        prepare_repo(repo, refresh=False)

    # One dataset for all models; its name must differ from the evaluation's.
    dataset = weave.Dataset(name=f"{suite_name}-tasks", rows=tasks)
    weave.publish(dataset)
    judge = judge or CompletionJudge()
    scorers = [judge, tool_call_scorer, efficiency_scorer]  # same objects for every model

    def _evaluate(spec: ModelSpec) -> tuple[dict[str, Any], str]:
        model = CodingAgentModel(
            name=f"agent-{spec.label}",
            label=spec.label,
            spec=spec.to_dict(),
            profile=profile,
            max_turns=max_turns,
            max_wall_s=max_wall_s,
            stream=stream,
            allow_any_command=allow_any_command,
            suite=suite_name,
        )
        evaluation = weave.Evaluation(
            name=f"{suite_name}-eval",
            dataset=dataset,
            scorers=scorers,
            trials=trials,
            evaluation_name=f"{spec.label} · {profile}",  # the compare view's column header
        )
        summary, call = _run_coroutine(evaluation.evaluate.call(evaluation, model))
        # Weave assigns evaluation_name as the call's display name, but when several
        # evaluations start concurrently the names get shuffled between calls (observed:
        # 3 of 4 columns mislabeled). Re-set it from the model this call actually ran.
        call.set_display_name(f"{spec.label} · {profile}")
        if on_model_done:
            on_model_done(spec.label, summary)
        return summary, call.id

    # All models run at the same time: faster, and every model sees the same provider
    # conditions instead of whichever model happens to run last absorbing a slowdown.
    with ThreadPoolExecutor(max_workers=len(specs)) as pool:
        outcomes = list(pool.map(_evaluate, specs))
    results: dict[str, Any] = {"models": {}, "call_ids": []}
    for spec, (summary, call_id) in zip(specs, outcomes, strict=True):
        results["models"][spec.label] = summary
        results["call_ids"].append(call_id)
    results["label_check"] = verify_labels(client, results["call_ids"])

    entity, proj = project.split("/", 1) if "/" in project else (client.entity, project)
    results["compare_url"] = compare_url(entity, proj, results["call_ids"])
    results["project_url"] = f"https://wandb.ai/{entity}/{proj}/weave/evaluations"
    return results


def verify_labels(client: Any, call_ids: list[str], fix: bool = True) -> list[dict[str, Any]]:
    """Check each evaluation call's display name names the model it actually ran.

    Reads the model from the call's recorded inputs (the source of truth) and,
    with ``fix=True``, corrects any display name that disagrees. Returns one
    row per call: ``{"call_id", "model", "display_name", "ok"}``.
    """
    rows = []
    for call_id in call_ids:
        call = client.get_call(call_id)
        model = call.inputs.get("model")
        label = getattr(model, "label", None)
        profile = getattr(model, "profile", None)
        expected = f"{label} · {profile}" if label and profile else None
        ok = expected is None or call.display_name == expected
        if not ok and fix:
            call.set_display_name(expected)
        rows.append({"call_id": call_id, "model": label, "display_name": call.display_name, "ok": ok})
    return rows


def collect_rows(suite: str | None = None) -> list[dict[str, Any]]:
    """One flat row per attempt (agent output joined with its judge verdict) for tables and charts."""
    from .agent import tool_call_accuracy

    with _LOCK:
        attempts = [a for a in ATTEMPTS.values() if suite is None or a.get("suite") == suite]
    rows = []
    for a in attempts:
        verdict = JUDGE_RESULTS.get(a["attempt_id"], {})
        events = a.get("events") or {}
        rows.append(
            {
                "model": a.get("model"),
                "profile": a.get("profile"),
                "task_id": a.get("task_id"),
                "mode": a.get("mode"),
                "category": a.get("category"),
                "passed": verdict.get("passed"),
                # No recorded verdict (scorer crashed) or the judge itself failed.
                "judge_error": (not verdict) or bool(verdict.get("judge_error")),
                "verdict": verdict.get("verdict"),
                "score": verdict.get("score"),
                "rationale": verdict.get("rationale"),
                "stop_reason": a.get("stop_reason"),
                "silent_stop": a.get("stop_reason") in ("dropped_tool_call", "leaked_tool_call"),
                "tool_call_accuracy": tool_call_accuracy(events),
                **{f"n_{k}": events.get(k, 0) for k in ("dropped", "leaked", "malformed_args", "truncated")},
                "repairs": a.get("repairs", 0),
                "nudges": a.get("nudges", 0),
                "turns": a.get("turns", 0),
                "output_tokens": a.get("output_tokens", 0),
                "wall_s": a.get("wall_s"),
                "ttft_s": a.get("ttft_s"),
                "cost_usd": a.get("cost_usd"),
                "judge_cost_usd": verdict.get("judge_cost_usd"),
                "diff_lines": a.get("diff_lines", 0),
                "error": a.get("error"),
                "attempt_id": a["attempt_id"],
            }
        )
    return rows


def leaderboard(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per (model, profile): completion, tool-call accuracy, speed, and cost per successful task."""
    import statistics

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r["model"], r["profile"]), []).append(r)
    board = []
    for (model, profile), rs in groups.items():
        # Every attempt stays in the denominator, as it does for cost: an attempt the judge
        # could not grade is not a pass. `unjudged` shows how many there were, so a flaky
        # judge is visible instead of silently inflating (or deflating) completion.
        passes = sum(bool(r["passed"]) for r in rs)
        unjudged = sum(bool(r.get("judge_error", r["passed"] is None)) for r in rs)
        costs = [r["cost_usd"] for r in rs]
        total = sum(costs) if all(c is not None for c in costs) else None
        accs = [r["tool_call_accuracy"] for r in rs if r["tool_call_accuracy"] is not None]
        walls = [r["wall_s"] for r in rs if r["wall_s"] is not None]
        board.append(
            {
                "model": model,
                "profile": profile,
                "attempts": len(rs),
                "unjudged": unjudged,
                "completion_rate": round(passes / len(rs), 3),
                "partial_rate": round(sum(r["verdict"] == "partial" for r in rs) / len(rs), 3),
                "tool_call_accuracy": round(statistics.fmean(accs), 3) if accs else None,
                "silent_stop_rate": round(sum(r["silent_stop"] for r in rs) / len(rs), 3),
                "median_wall_s": round(statistics.median(walls), 1) if walls else None,
                "mean_turns": round(statistics.fmean(r["turns"] for r in rs), 1),
                "output_tokens_per_task": round(statistics.fmean(r["output_tokens"] for r in rs)),
                "cost_per_attempt": round(total / len(rs), 4) if total is not None else None,
                "cost_per_success": round(total / passes, 4) if (total is not None and passes) else None,
            }
        )
    return sorted(board, key=lambda b: (-(b["completion_rate"] or 0), b["cost_per_success"] or float("inf")))


def escalation_ladder(rows: list[dict[str, Any]], order: list[str] | None = None) -> dict[str, Any]:
    """Simulate "cheapest model first, escalate on failure" from per-task results.

    For each task, a model's pass rate and mean cost per attempt come from its
    trials. The ladder tries models in ``order`` (default: cheapest mean cost
    per attempt first) and stops at the first pass, so its expected cost per task
    is ``c1 + (1-p1)*c2 + (1-p1)*(1-p2)*c3 + ...`` and its success probability is
    ``1 - prod(1 - p)``.

    This assumes failures are detectable (by tests, a reviewer, or a judge) —
    the best case for routing. Compare its ``cost_per_success`` with the single
    best model's before buying a router.
    """
    from collections import defaultdict

    per: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r.get("passed") is not None and r.get("cost_usd") is not None:
            per[(r["task_id"], r["model"])].append(r)
    models = sorted({m for _, m in per})
    if order is None:
        mean_cost = {
            m: sum(r["cost_usd"] for (t, mm), rs in per.items() if mm == m for r in rs)
            / max(1, sum(len(rs) for (t, mm), rs in per.items() if mm == m))
            for m in models
        }
        order = sorted(models, key=lambda m: mean_cost[m])
    tasks = sorted({t for t, _ in per})
    total_cost = total_success = 0.0
    for t in tasks:
        reach, cost = 1.0, 0.0
        for m in order:
            rs = per.get((t, m))
            if not rs:
                continue
            p = sum(bool(r["passed"]) for r in rs) / len(rs)
            c = sum(r["cost_usd"] for r in rs) / len(rs)
            cost += reach * c
            reach *= 1 - p
        total_cost += cost
        total_success += 1 - reach
    return {
        "order": order,
        "tasks": len(tasks),
        "expected_completion_rate": round(total_success / len(tasks), 3) if tasks else None,
        "expected_cost_per_task": round(total_cost / len(tasks), 4) if tasks else None,
        "cost_per_success": round(total_cost / total_success, 4) if total_success else None,
    }
