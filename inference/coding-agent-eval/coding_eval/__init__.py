"""Coding-agent evaluation kit: pick an open model from your own merged PRs.

Pipeline:
    tasks.build_tasks      merged PRs -> replayable tasks (prompt, base commit, reference diff)
    probe.run_probe        one-minute check that tool calls survive your serving stack
    evaluate.run_suite     N models x tasks x trials through an instrumented harness, in Weave
    grading                frontier-model judge + tool-call + efficiency scorers

See ``notebook.py`` next to this package for the guided marimo notebook.
"""

from .agent import RunConfig, Trajectory, run_agent, tool_call_accuracy
from .grading import CompletionJudge, efficiency_scorer, tool_call_scorer
from .models import CLOSED_PRESETS, DEFAULT_LINEUP, PRESETS, SI_BASE_URL, SI_PRESETS, ModelSpec
from .probe import run_probe, summarize_probe
from .tasks import build_tasks, load_tasks, prepare_repo, save_tasks

__all__ = [
    "CLOSED_PRESETS",
    "DEFAULT_LINEUP",
    "PRESETS",
    "SI_BASE_URL",
    "SI_PRESETS",
    "CompletionJudge",
    "ModelSpec",
    "RunConfig",
    "Trajectory",
    "build_tasks",
    "efficiency_scorer",
    "load_tasks",
    "prepare_repo",
    "run_agent",
    "run_probe",
    "save_tasks",
    "summarize_probe",
    "tool_call_accuracy",
    "tool_call_scorer",
]
