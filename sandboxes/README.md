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

### 4. [`claude-remote-control-tutorial.py`](./claude-remote-control-tutorial.py)

A step-by-step, interactive tutorial for turning a Serverless Sandbox into the
remote machine your Claude Code session runs on. Walks through connecting W&B,
creating the sandbox (`Sandbox.run()`) with public ingress on port 8080,
installing Claude Code (`sandbox.exec()`), signing in and launching
[Remote Control](https://code.claude.com/docs/en/remote-control) over a PTY
(`sandbox.shell()`), then having Claude build and serve a live website reachable
at `sandbox.service_address`, and finally cleaning up (`sandbox.stop()`). The
OAuth login and the `Enable Remote Control?` prompt are handled inline in the
notebook.

**Use Case:** Steering Claude Code from [claude.ai/code](https://claude.ai/code)
or the Claude mobile app while execution stays in a cloud sandbox.

## Scripts

### 1. [`claude-remote-control-script.py`](./claude-remote-control-script.py)

The compact, no-frills version of the tutorial above: provisions a sandbox,
installs Claude Code, pre-trusts `/workspace`, and attaches your local terminal
to a PTY inside the sandbox so you can sign in and run `claude remote-control`.
Stops the sandbox on exit.

**Use Case:** Launching a remote Claude Code session from your terminal in one
command, without the notebook UI.

## Getting Started

1. From the repo root, install dependencies: `uv sync`
2. Open a notebook in the marimo editor: `uv run marimo edit sandboxes/serverless-sandboxes-tutorial.py`
3. When prompted about inlined package dependencies, answer `n` to use the project environment (or `Y` for an isolated venv built from the notebook's inline dependencies).

Scripts run directly in the project environment:

```bash
uv run python sandboxes/claude-remote-control-script.py
```
