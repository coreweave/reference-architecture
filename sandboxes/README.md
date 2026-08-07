# CoreWeave Sandboxes Examples

This directory contains marimo notebooks and scripts demonstrating different use cases for [CoreWeave Sandboxes](https://docs.coreweave.com/products/sandboxes), isolated, on-demand execution environments for agentic workloads.

## Notebooks

### 1. [`serverless-sandboxes-tutorial.py`](./serverless-sandboxes-tutorial.py)

An end-to-end code-evaluation workflow: a hosted model (via Serverless Inference's OpenAI-compatible API) generates Python for benchmark tasks, the generated code runs against deterministic tests inside a Serverless Sandbox, and every step is traced and scored in W&B Weave for side-by-side model comparison.

**Use Case:** Evaluating hosted code-generation models with safe, isolated code execution.

### 2. [`harness-evals.py`](./harness-evals.py)

Evaluates full coding-agent CLIs (Codex, Claude Code, OpenClaw, Nous Hermes) that each live inside their own sandbox. Solutions are scored in a separate, network-isolated sandbox against demo tasks or the HumanEval / MBPP benchmarks, with per-agent `weave.Evaluation` runs.

**Use Case:** Benchmarking and comparing agent harnesses on coding tasks at scale.

### 3. [`devin-outpost.py`](./devin-outpost.py)

Creates a Serverless Sandbox from Devin's official CLI image and connects it as
a single Linux worker for an existing Devin Outpost, with bounded resources and
explicit cleanup.

**Use Case:** Running Devin sessions inside an isolated, on-demand development
environment.
