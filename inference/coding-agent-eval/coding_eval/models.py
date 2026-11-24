"""Model endpoints under evaluation.

A ``ModelSpec`` describes one model to put through the eval: where it is served,
how to authenticate, and what it costs. Open models are reached through any
OpenAI-compatible endpoint (CoreWeave Serverless Inference, a Dedicated
Inference gateway, vLLM on CKS, OpenRouter, ...). Claude models are reached
through the Anthropic SDK.

Prices are USD per 1M tokens. Serverless Inference defaults below were copied
from https://coreweave.com/forge-pricing/inference-agents on 2026-11-17 —
prices change, so treat them as a starting point and edit them in the notebook.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal

SI_BASE_URL = "https://api.inference.wandb.ai/v1"

Provider = Literal["openai", "anthropic"]


@dataclass(frozen=True)
class ModelSpec:
    """One model endpoint to evaluate.

    Args:
        label: Short, unique display name. Becomes the Weave evaluation name.
        model: Model ID sent in the request (e.g. ``moonshotai/Kimi-K2.7-Code``).
        provider: ``"openai"`` for any OpenAI-compatible endpoint, ``"anthropic"`` for Claude.
        base_url: Endpoint root for OpenAI-compatible providers (ignored for Anthropic).
        api_key_env: Environment variable holding the API key.
        project: Optional ``OpenAI-Project`` header (Serverless Inference usage tracking).
        input_price: USD per 1M uncached input tokens.
        output_price: USD per 1M output tokens.
        cached_input_price: USD per 1M cached input tokens (falls back to ``input_price``).
        max_output_tokens: Per-turn output cap.
        extra_body: Extra request fields (e.g. ``{"reasoning_effort": "medium"}``).
        closed: True for the closed-model baseline (used for labeling only).
    """

    label: str
    model: str
    provider: Provider = "openai"
    base_url: str | None = SI_BASE_URL
    api_key_env: str = "SI_API_KEY"
    project: str | None = None
    input_price: float | None = None
    output_price: float | None = None
    cached_input_price: float | None = None
    max_output_tokens: int = 32768  # reasoning models spend much of a turn's budget thinking
    extra_body: dict[str, Any] = field(default_factory=dict)
    closed: bool = False

    def api_key(self) -> str | None:
        """The API key from ``api_key_env``, or None if unset.

        Serverless Inference accepts a W&B API key, so SI specs fall back to
        ``WANDB_API_KEY`` when ``SI_API_KEY`` is not set. Set ``project``
        (``team/project``, sent as ``OpenAI-Project``) to attribute usage; it is
        needed when the account belongs to more than one team, where a request
        without it can be rejected with a misleading ``401 invalid_api_key``.
        """
        key = os.environ.get(self.api_key_env)
        if not key and self.api_key_env == "SI_API_KEY":
            key = os.environ.get("WANDB_API_KEY")
        return key

    def cost(self, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> float | None:
        """USD cost of one request, or None when pricing is unknown."""
        if self.input_price is None or self.output_price is None:
            return None
        cached_price = self.cached_input_price if self.cached_input_price is not None else self.input_price
        uncached = max(input_tokens - cached_input_tokens, 0)
        return (
            uncached * self.input_price + cached_input_tokens * cached_price + output_tokens * self.output_price
        ) / 1e6

    def with_overrides(self, **kwargs: Any) -> ModelSpec:
        """Copy of this spec with fields replaced."""
        return replace(self, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict form (used as a Weave Model field)."""
        return asdict(self)


def _si(label: str, model: str, inp: float, out: float, cached: float | None = None) -> ModelSpec:
    return ModelSpec(label=label, model=model, input_price=inp, output_price=out, cached_input_price=cached)


# Open models on CoreWeave Serverless Inference that are positioned for agentic coding.
SI_PRESETS: dict[str, ModelSpec] = {
    s.label: s
    for s in [
        _si("kimi-k2.7-code", "moonshotai/Kimi-K2.7-Code", 0.60, 3.00, 0.12),
        _si("glm-5.3", "zai-org/GLM-5.3", 0.75, 3.00, 0.19),
        _si("glm-5.3-flash", "zai-org/GLM-5.3-Flash", 0.12, 0.38, 0.02),
        _si("minimax-m3", "MiniMaxAI/MiniMax-M3", 0.23, 0.96, 0.05),
        _si("deepseek-v4.1-flash", "deepseek-ai/DeepSeek-V4.1-Flash", 0.13, 0.65, 0.002),
        _si("deepseek-v4-pro", "deepseek-ai/DeepSeek-V4-Pro-0813", 1.31, 3.96, 0.044),
        _si("qwen3.6-35b-a3b", "Qwen/Qwen3.6-35B-A3B", 0.10, 0.89, 0.035),
        _si("qwen3.8-27b", "Qwen/Qwen3.8-27B", 0.40, 3.00, 0.15),
        _si("nemotron-3-ultra", "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B", 0.50, 2.15, 0.10),
        _si("gpt-oss-120b", "openai/gpt-oss-120b", 0.03, 0.17),
    ]
}

# Closed-model baselines. Anthropic list prices (USD / 1M tokens).
CLOSED_PRESETS: dict[str, ModelSpec] = {
    "claude-opus-5.5": ModelSpec(
        label="claude-opus-5.5",
        model="claude-opus-5-5",
        provider="anthropic",
        base_url=None,
        api_key_env="ANTHROPIC_API_KEY",
        input_price=4.00,
        output_price=20.00,
        cached_input_price=0.20,
        max_output_tokens=16000,
        closed=True,
    ),
    "claude-sonnet-5.5": ModelSpec(
        label="claude-sonnet-5.5",
        model="claude-sonnet-5-5",
        provider="anthropic",
        base_url=None,
        api_key_env="ANTHROPIC_API_KEY",
        input_price=2.00,
        output_price=10.00,
        cached_input_price=0.10,
        max_output_tokens=16000,
        closed=True,
    ),
}

PRESETS: dict[str, ModelSpec] = {**SI_PRESETS, **CLOSED_PRESETS}

# Three open coding models plus the closed baseline: a strong coder, a large
# generalist, and a cheap fast model (the class most likely to drop tool calls).
DEFAULT_LINEUP = ["kimi-k2.7-code", "glm-5.3", "glm-5.3-flash", "claude-opus-5.5"]
