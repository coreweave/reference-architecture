# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "cwsandbox==0.25.0",
#     "marimo>=0.23.8",
#     "pydantic==2.13.4",
#     "wandb[sandbox]==0.27.2",
#     "weave==0.52.38",
# ]
# ///

import marimo

__generated_with = "0.23.14"
app = marimo.App(
    width="medium",
    app_title="Agent Harness Evals",
    css_file="/usr/local/_marimo/custom.css",
    auto_download=["html"],
)


@app.cell
def _():
    import os
    import time
    import json
    import uuid
    import weave
    import marimo as mo
    from pydantic import PrivateAttr
    from wandb.sandbox import (
        Sandbox,
        SandboxDefaults,
        ResourceOptions,
        NetworkOptions,
        SandboxTimeoutError,
        SandboxExecutionError,
        SandboxError,
    )

    return (
        NetworkOptions,
        PrivateAttr,
        ResourceOptions,
        Sandbox,
        SandboxDefaults,
        SandboxError,
        SandboxExecutionError,
        SandboxTimeoutError,
        json,
        mo,
        os,
        time,
        uuid,
        weave,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                r"""
                # Evaluating Coding Agents Inside Serverless Sandboxes

                /// admonition | About This Notebook
                    type: info

                This notebook is the agent-centric full coding-agent CLI that lives inside its own sandbox**:

                - The sandbox is provisioned the moment the `weave.Model` is initialized.
                - The agent binary is installed and authenticated **headlessly**, no
                  user-led onboarding, just a W&B API key is needed.
                - Every `predict` drives the agent *inside that sandbox* to write a solution,
                  which is then scored safely in a separate, network-isolated sandbox.

                Four harnesses are wired up: **Codex**, **Claude Code**, **OpenClaw**, and
                **Nous Hermes**, and you can score them on the built-in demo tasks or the
                **HumanEval** / **MBPP** benchmarks (selected below).

                _If you are running this notebook in edit mode, make sure you start by running all cells._
                ///
                """
            ),
            mo.md(
                r"""
                /// details | Prerequisites
                    type: info

                - **A W&B account + API key** — from [wandb.ai/authorize](https://wandb.ai/authorize).
                - **Provider API keys** — an OpenAI key for Codex, OpenClaw, Hermes and/or an Anthropic key for
                  Claude. Paste whichever you need into the Connect form below; an agent is only
                  runnable if its key is present.
                ///
                """
            ),
            mo.md(
                r"""
                /// details | Table of Contents
                    type: info

                - [**Connect W&B services and provider keys**](#1-connect-wb-services-and-provider-keys) - Authenticate agents headlessly
                - [**Define the agent backends**](#2-define-the-agent-backends) - The `AgentBackend` extensibility seam
                - [**Score generated code safely in a separate sandbox**](#3-score-generated-code-safely-in-a-separate-sandbox) - Isolated verification
                - [**Benchmark tasks**](#4-benchmark-tasks) - Demo, HumanEval, and MBPP
                - [**Pick agents and launch an evaluation**](#5-pick-agents-and-launch-an-evaluation) - Run per-agent `weave.Evaluation`
                - [**Lifecycle, discovery, and cleanup**](#6-lifecycle-discovery-and-cleanup) - Find and stop sandboxes
                ///
                """
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    # ---------- 1. Setup W&B + provider keys ----------
    wandb_connect_form = (
        mo.md("""
        - W&B entity *(team or username)*: {entity}
        - W&B project: {project}
        - W&B API key *(required)*: {api_key}
        - OpenAI API key *(for Codex, OpenClaw, Hermes)*: {openai_api_key}
        - Anthropic API key *(for Claude)*: {anthropic_api_key}
        """)
        .batch(
            entity=mo.ui.text(value="wandb-smle", full_width=True),
            project=mo.ui.text(value="agent-sandbox-eval", full_width=True),
            api_key=mo.ui.text(kind="password", placeholder="from wandb.ai/authorize", full_width=True),
            openai_api_key=mo.ui.text(kind="password", placeholder="sk-...", full_width=True),
            anthropic_api_key=mo.ui.text(kind="password", placeholder="sk-ant-...", full_width=True),
        )
        .form(submit_button_label="Connect", bordered=False)
    )
    wandb_connect_form
    return (wandb_connect_form,)


@app.cell(hide_code=True)
def _(mo, os, wandb_connect_form, weave):
    _v = wandb_connect_form.value or {}
    ENTITY = _v.get("entity")
    PROJECT = _v.get("project")
    API_KEY = _v.get("api_key")
    mo.stop(
        not (ENTITY and PROJECT and API_KEY),
        mo.md("_Fill in the W&B fields above and press **Connect**._"),
    )

    os.environ["WANDB_API_KEY"] = API_KEY
    weave.init(f"{ENTITY}/{PROJECT}")
    weave_url = f"https://wandb.ai/{ENTITY}/{PROJECT}/weave"

    PROVIDER_KEYS = {
        "openai_api_key": _v.get("openai_api_key") or "",
        "anthropic_api_key": _v.get("anthropic_api_key") or "",
    }
    _have = [n for n, k in PROVIDER_KEYS.items() if k]

    mo.callout(
        mo.md(
            f"✅ **Connected** — logging to `{ENTITY}/{PROJECT}`. "
            f"[Open Weave dashboard]({weave_url})  \n"
            f"Provider keys provided: `{', '.join(_have) or 'none yet'}`"
        ),
        kind="success",
    )
    return API_KEY, PROVIDER_KEYS


@app.cell(hide_code=True)
def _(mo):
    mo.md(f"""
    ---
    ## 1. Connect W&B services and provider keys

    /// admonition | Connect and authenticate agents
        type: info

    Fill in your W&B entity, project, and API key, plus the provider key(s) for
    the agent(s) you want to run, then press **Connect**. Keys are kept in memory
    and injected into each agent's sandbox as environment variables
    (`OPENAI_API_KEY` for Codex, `ANTHROPIC_API_KEY` for
    Claude). Nothing is written to disk and no interactive login is triggered.

    The form gates the rest of the notebook: the agent definitions, scorer, and
    evaluation cells stay paused until you connect.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    wandb_product_tabs = mo.ui.tabs(
        {
            "Agents": mo.md(
                """
                ### Coding agents as sandboxed models

                Each agent is a real terminal coding tool driven headlessly
                (`codex exec`, `claude -p`). Inside its sandbox the agent reads the
                task, writes Python, and saves a final `solution.py`, exactly the
                workflow a developer would run locally, but isolated and reproducible.
                """
            ),
            "Weave": mo.md(
                """
                ### W&B Weave

                Weave traces the full lifecycle: the agent's generation
                (`predict`), the returned solution, the scorer's pass/fail verdict,
                and latency — making it easy to compare agents side by side.
                """
            ),
            "Sandbox": mo.md(
                """
                ### Serverless Sandbox

                Two sandbox roles here: the **agent sandbox** (one per model,
                provisioned at init, internet egress enabled so the agent can call
                its model API and `npm install`) and the **scorer sandbox** (a
                fresh, network-isolated sandbox per scored solution, so untrusted
                generated code can't phone home).
                """
            ),
        }
    )

    wandb_product_tabs
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(f"""
    ---
    ## 2. Define the agent backends

    /// admonition | AgentBackend
        type: info

    `AgentBackend` is the extensibility seam: each concrete backend knows how to
    **install** itself, what **auth env** it needs, and how to build the headless
    **run command**.
    ///
    """)
    return


@app.cell
def _():
    # ---------- 2.1 Agent backend abstraction ----------
    import shlex
    from abc import ABC, abstractmethod

    class AgentBackend(ABC):
        id: str
        display_name: str
        provider: str
        key_field: str 
        eval_parallelism: int | None = None
        run_timeout_seconds: int | None = None

        @abstractmethod
        def install_cmds(self) -> list:
            """Commands run once inside the sandbox at provision time."""

        @abstractmethod
        def auth_env(self, api_key: str) -> dict:
            """Env vars (baked into the agent sandbox) for non-interactive auth."""

        @abstractmethod
        def run_argv(self, prompt: str, workdir: str, model: str | None) -> list:
            """argv to run the agent headlessly for a single task."""

    class CodexBackend(AgentBackend):
        id = "codex"
        display_name = "Codex CLI"
        provider = "OpenAI"
        key_field = "openai_api_key"

        def install_cmds(self) -> list:
            return [["npm", "install", "-g", "@openai/codex"]]

        def auth_env(self, api_key: str) -> dict:
            return {"CODEX_API_KEY": api_key, "OPENAI_API_KEY": api_key}

        def run_argv(self, prompt: str, workdir: str, model: str | None) -> list:
            # We're already inside an isolated W&B sandbox, so disable Codex's OWN
            # nested OS sandbox (landlock/seccomp).
            argv = [
                "codex", "exec",
                "--skip-git-repo-check",
                "--sandbox", "danger-full-access",
                "--cd", workdir,
            ]
            if model:
                argv += ["-m", model]
            argv.append(prompt)
            return argv

    class ClaudeCodeBackend(AgentBackend):
        id = "claude"
        display_name = "Claude Code CLI"
        provider = "Anthropic"
        key_field = "anthropic_api_key"

        def install_cmds(self) -> list:
            return [["npm", "install", "-g", "@anthropic-ai/claude-code"]]

        def auth_env(self, api_key: str) -> dict:
            # IS_SANDBOX=1 is Claude Code's documented escape hatch: W&B sandbox
            # runs as root
            return {"ANTHROPIC_API_KEY": api_key, "IS_SANDBOX": "1"}

        def run_argv(self, prompt: str, workdir: str, model: str | None) -> list:
            inner = ["claude", "-p", prompt, "--bare", "--dangerously-skip-permissions"]
            if model:
                inner += ["--model", model]
            return ["bash", "-lc", f"cd {shlex.quote(workdir)} && {shlex.join(inner)}"]

    class OpenClawBackend(AgentBackend):
        # OpenClaw is a full agent HARNESS (Gateway + workspace + tools)
        id = "openclaw"
        display_name = "OpenClaw"
        eval_parallelism = 1  
        run_timeout_seconds = 300
        provider = "OpenAI"
        key_field = "openai_api_key"

        workspace = "/work/openclaw-ws"

        def install_cmds(self) -> list:
            onboard = (
                f"mkdir -p {shlex.quote(self.workspace)} && "
                "openclaw onboard --non-interactive --mode local "
                f"--workspace {shlex.quote(self.workspace)} "
                "--auth-choice openai-api-key --secret-input-mode ref "
                "--accept-risk --skip-skills --skip-bootstrap --skip-health"
            )
            return [
                ["npm", "install", "-g", "openclaw@latest"],
                ["bash", "-lc", onboard],
            ]

        def auth_env(self, api_key: str) -> dict:
            return {"OPENAI_API_KEY": api_key}

        def run_argv(self, prompt: str, workdir: str, model: str | None) -> list:
            return [
                "bash", "-lc",
                f"openclaw agent --local --agent main --message {shlex.quote(prompt)}",
            ]

    class HermesBackend(AgentBackend):
        # Hermes (Nous Research) is a self-improving agent harness
        id = "hermes"
        display_name = "Hermes (Nous)"
        provider = "OpenAI"
        key_field = "openai_api_key"
        hermes_provider = "openai-api"
        default_model = "gpt-5.5"

        def install_cmds(self) -> list:
            return [[
                "bash", "-lc",
                "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash",
            ]]

        def auth_env(self, api_key: str) -> dict:
            return {
                "OPENAI_API_KEY": api_key,
                "HERMES_YOLO_MODE": "1",     # bypass dangerous-command approval
                "HERMES_ACCEPT_HOOKS": "1",  # auto-approve shell hooks (no TTY)
            }

        def run_argv(self, prompt: str, workdir: str, model: str | None) -> list:
            m = model or self.default_model
            cmd = (
                f"hermes -z {shlex.quote(prompt)} "
                f"--provider {self.hermes_provider} --model {shlex.quote(m)}"
            )
            return [
                "bash", "-lc",
                'export PATH="$HOME/.local/bin:$PATH" && '
                f"cd {shlex.quote(workdir)} && {cmd}",
            ]

    BACKENDS = {
        b.id: b
        for b in (CodexBackend(), ClaudeCodeBackend(), OpenClawBackend(), HermesBackend())
    }
    return (BACKENDS,)


@app.cell
def _(ResourceOptions):
    # Agent sandboxes need Node (for the CLIs) and git; node:22-bookworm has both.
    # They get more CPU/memory than the scorer because they run a full agent loop.
    # ONE sandbox per model serves all concurrent predicts (see DEFAULT_PARALLELISM),
    # and each `claude`/`codex`/`openclaw`/`hermes` run is a heavy Node/Rust process, so the
    # LIMITS are generous to avoid OOM-killing concurrent agents (which manifests as
    # empty-output timeouts). Requests stay small so provisioning isn't rejected.
    AGENT_IMAGE = "node:22-bookworm"
    AGENT_RESOURCES = ResourceOptions(
        requests={"cpu": "500m", "memory": "512Mi"},
        limits={"cpu": "4", "memory": "6Gi"},
    )
    return AGENT_IMAGE, AGENT_RESOURCES


@app.cell
def _(
    AGENT_IMAGE,
    AGENT_RESOURCES,
    BACKENDS,
    NetworkOptions,
    PrivateAttr,
    Sandbox,
    SandboxDefaults,
    SandboxTimeoutError,
    uuid,
    weave,
):
    # ---------- 2.2 Sandboxed-agent weave.Model ----------
    import hashlib
    import threading

    _AGENT_SANDBOXES: dict = {}
    _PROVISION_LOCK = threading.Lock()

    AGENT_MAX_LIFETIME_SECONDS = 3600

    class SandboxAgentModel(weave.Model):
        agent_id: str
        model_name: str | None = None
        # Two independent budgets: a one-time CLI install vs. each agent task run.
        # Codex/Claude return in seconds on these tasks, so 180s is a generous run 
        # ceiling that fails fast if one hangs.
        install_timeout_seconds: int = 900
        run_timeout_seconds: int = 180
        # Sandbox self-termination backstop. Defaults to the floor; the run loop
        # raises it for serial agents so the sandbox outlives the full eval.
        max_lifetime_seconds: int = AGENT_MAX_LIFETIME_SECONDS
        # Serialized link: the sandbox this agent is bound to. Set during setup();
        # lets us re-attach (Sandbox.from_id) and stop() the exact sandbox at any
        # time. (It changes per run, so each run logs a new model version.)
        sandbox_id: str | None = None

        # Private (not serialized): the provider key, kept out of the trace/version.
        _api_key: str = PrivateAttr(default="")

        # ---- lifecycle ----
        def _cache_key(self) -> tuple:
            digest = (
                hashlib.sha256(self._api_key.encode()).hexdigest()[:8]
                if self._api_key
                else "nokey"
            )
            return (self.agent_id, self.model_name, digest)

        def _provision(self):
            """Spin up the agent's sandbox and install + authenticate the CLI once."""
            backend = BACKENDS[self.agent_id]
            defaults = SandboxDefaults(
                container_image=AGENT_IMAGE,
                tags=("agent-sandbox-eval", self.agent_id),
                environment_variables={
                    **backend.auth_env(self._api_key),
                    "NODE_NO_WARNINGS": "1",
                    "CI": "1",
                },
                resources=AGENT_RESOURCES,
            )
            # Internet egress: required for npm install AND the agent's model API.
            sb = Sandbox.run(
                defaults=defaults,
                network=NetworkOptions(egress_mode="internet"),
                max_lifetime_seconds=self.max_lifetime_seconds,
            )
            for cmd in backend.install_cmds():
                proc = sb.exec(cmd, timeout_seconds=self.install_timeout_seconds).result()
                if proc.returncode != 0:
                    try:
                        sb.stop(missing_ok=True).result()
                    except Exception:
                        pass
                    raise RuntimeError(
                        f"`{' '.join(cmd)}` failed (rc={proc.returncode}): "
                        f"{(proc.stderr or '')[-400:]}"
                    )
            return sb

        @weave.op(name="agent_setup")
        def setup(self) -> dict:
            """Lazily spin up + install + authenticate the agent's sandbox once, then
            cache the handle and bind self.sandbox_id to it. Wrapped as a weave.op so
            provisioning (and any failure) is traced as OUTPUT rather than raising and
            crashing the run. Idempotent: reuses a cached/known sandbox if present."""
            key = self._cache_key()
            sb = _AGENT_SANDBOXES.get(key)
            if sb is None:
                with _PROVISION_LOCK:
                    sb = _AGENT_SANDBOXES.get(key)  # re-check after acquiring the lock
                    if sb is None:
                        try:
                            if self.sandbox_id is not None:
                                # Known id, no cached handle (fresh process) -> reattach.
                                sb = Sandbox.from_id(self.sandbox_id).result()
                            else:
                                sb = self._provision()
                        except Exception as e:
                            return {
                                "agent_id": self.agent_id,
                                "model_name": self.model_name,
                                "status": "error",
                                "error": f"{type(e).__name__}: {e}",
                            }
                        _AGENT_SANDBOXES[key] = sb
            self.sandbox_id = sb.sandbox_id
            return {
                "agent_id": self.agent_id,
                "model_name": self.model_name,
                "sandbox_id": self.sandbox_id,
                "status": "ready",
            }

        def _get_sandbox(self):
            """Return (live_handle_or_None, setup_status). Provisions via setup() on
            first use; predict relies on this so a setup failure becomes a failed row
            instead of an exception."""
            sb = _AGENT_SANDBOXES.get(self._cache_key())
            if sb is not None:
                self.sandbox_id = sb.sandbox_id
                return sb, {"status": "ready", "sandbox_id": self.sandbox_id}
            status = self.setup()
            return _AGENT_SANDBOXES.get(self._cache_key()), status

        def ensure_ready(self) -> dict:
            """Public hook for the run loop to provision before evaluate (clean error
            reporting + keeps the first row's latency from absorbing the install).
            Returns the setup() status dict."""
            return self.setup()

        @weave.op(name="agent_generate_solution", kind="llm")
        def predict(self, name: str, spec: str, tests: list) -> str:
            import shlex as _shlex

            backend = BACKENDS[self.agent_id]
            sb, status = self._get_sandbox()
            if sb is None:
                return f"failed: setup error: {status.get('error', 'unknown')}"

            run_id = uuid.uuid4().hex
            workdir = f"/work/{run_id}"
            target = f"{workdir}/solution.py"
            # Logs live OUTSIDE workdir so the agent doesn't see/touch them.
            out_log, err_log = f"/tmp/{run_id}.out", f"/tmp/{run_id}.err"
            try:
                sb.exec(["mkdir", "-p", workdir]).result()
            except Exception as e:  # noqa: BLE001
                # The sandbox can be GONE here — e.g. it hit max_lifetime_seconds
                # mid-eval (serial agents) and the gRPC call returns NOT_FOUND.
                # Record a failed row instead of letting it crash the eval thread.
                return (
                    f"failed: agent sandbox unavailable ({type(e).__name__}); it may "
                    f"have exceeded its lifetime. {str(e)[-200:]}"
                )

            prompt = (
                f"You are solving a coding task. Write a Python function "
                f"named `{name}` that satisfies the specification below.\n\n"
                f"Specification:\n{spec}\n\n"
                f"Requirements:\n"
                f"- Use the exact function name and signature requested.\n"
                f"- Save the complete solution — the function definition plus any "
                f"imports it needs (no markdown fences, no prose) — to the file: "
                f"{target}\n"
                f"- Overwrite the file if it already exists.\n"
            )
            argv = backend.run_argv(prompt, workdir, self.model_name)
            shell = (
                f"{_shlex.join(argv)} < /dev/null "
                f"> {_shlex.quote(out_log)} 2> {_shlex.quote(err_log)}"
            )

            def _tail(path: str, n: int = 500) -> str:
                try:
                    return sb.read_file(path).result().decode()[-n:].strip()
                except Exception:
                    return ""

            try:
                sb.exec(
                    ["bash", "-lc", shell], timeout_seconds=self.run_timeout_seconds
                ).result()
            except SandboxTimeoutError:
                # Catch the PARENT timeout (covers SandboxCommandTimeoutError too) so a
                # slow/hung agent records a failed row (with diagnostics) instead of
                # crashing the eval. Capture BOTH streams
                return (
                    f"failed: agent run timed out after {self.run_timeout_seconds}s. "
                    f"stdout tail: {_tail(out_log)} | stderr tail: {_tail(err_log)}"
                )
            except Exception as e:  # noqa: BLE001
                # Sandbox vanished during the run (e.g. lifetime exceeded -> NOT_FOUND).
                return (
                    f"failed: agent sandbox error during run ({type(e).__name__}); it "
                    f"may have exceeded its lifetime. {str(e)[-200:]}"
                )

            # Prefer the file the agent wrote; surface both streams otherwise.
            try:
                code = sb.read_file(target).result().decode()
                if code.strip():
                    return code.strip()
            except Exception:
                pass
            # Show what (if anything) the agent left in the workdir — distinguishes
            # "wrote nothing" from "wrote a differently-named file" at a glance.
            try:
                _ls = (
                    sb.exec(["bash", "-lc", f"ls -la {_shlex.quote(workdir)}"])
                    .result()
                    .stdout
                    or ""
                ).strip()[-200:]
            except Exception:
                _ls = ""
            return (
                f"failed: no solution.py written. workdir: {_ls} | "
                f"stdout tail: {_tail(out_log)} | stderr tail: {_tail(err_log)}"
            )

        def stop(self) -> None:
            """Spin down the sandbox bound to this agent — via the cached handle or,
            if that's gone, by re-attaching with the serialized sandbox_id."""
            sb = _AGENT_SANDBOXES.pop(self._cache_key(), None)
            if sb is None and self.sandbox_id:
                try:
                    sb = Sandbox.from_id(self.sandbox_id).result()
                except Exception:
                    sb = None
            if sb is not None:
                try:
                    sb.stop(missing_ok=True).result()
                except Exception:
                    pass


    return (SandboxAgentModel,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 3. Score generated code safely in a separate sandbox

    /// admonition | CodeScorer
        type: info

    The agent's output is verified by the **`CodeScorer`**: it wraps each task's `(input, expected)` pairs in a
    harness, runs the solution in a **fresh, network-isolated** sandbox, and
    returns `{passed, error, sandbox_latency}`. Keeping scoring in its own
    egress-free sandbox means untrusted generated code can't reach the network,
    even though the agent sandbox can.
    ///
    """)
    return


@app.cell
def _(ResourceOptions, SandboxDefaults):
    # Scorer sandboxes: small, no special networking (isolated by default).
    SANDBOX_DEFAULTS = SandboxDefaults(
        container_image="python:3.11",
        tags=("agent-sandbox-eval", "code-eval"),
        environment_variables={"PYTHONUNBUFFERED": "1"},
        resources=ResourceOptions(
            requests={"cpu": "250m", "memory": "256Mi"},
            limits={"cpu": "1", "memory": "512Mi"},
        ),
    )
    return (SANDBOX_DEFAULTS,)


@app.cell
def _(
    SANDBOX_DEFAULTS,
    Sandbox,
    SandboxError,
    SandboxExecutionError,
    SandboxTimeoutError,
    json,
    time,
    weave,
):
    # ---------- 3.1 Sandbox-based scorer ----------
    class CodeScorer(weave.Scorer):

        @weave.op(name="code_scorer", kind="scorer")
        def score(
            self,
            name: str,
            spec: str,
            tests: list,
            output: str,
            test_program: str | None = None,
            entry_point: str | None = None,
        ) -> dict:
            start_time = time.time()
            _out = (output or "").strip()
            if not _out or _out.startswith("failed:"):
                return {
                    "passed": False,
                    "error": (_out or "empty generation")[-300:],
                    "sandbox_latency": time.time() - start_time,
                }


            if test_program:
                _ep = entry_point or name
                script = (
                    f"{output}\n\n"
                    f"{test_program}\n\n"
                    "import json\n"
                    "_passed, _error = True, ''\n"
                    "try:\n"
                    f"    check({_ep})\n"
                    "except Exception as _e:\n"
                    "    _passed, _error = False, repr(_e)\n"
                    "with open('/tmp/result.json', 'w') as _f:\n"
                    "    json.dump({'passed': _passed, 'error': _error}, _f)\n"
                )
            else:
                asserts = "\n".join(
                    f"    assert {name}(*{args!r}) == {expected!r}, {f'failed on input {args!r}'!r}"
                    for args, expected in tests
                )
                script = (
                    f"{output}\n\n"
                    "import json\n"
                    "_passed, _error = True, ''\n"
                    "try:\n"
                    f"{asserts}\n"
                    "except Exception as _e:\n"
                    "    _passed, _error = False, repr(_e)\n"
                    "with open('/tmp/result.json', 'w') as _f:\n"
                    "    json.dump({'passed': _passed, 'error': _error}, _f)\n"
                )

            last_exc = None
            for attempt in range(3):
                sb = None
                try:
                    sb = Sandbox.run(defaults=SANDBOX_DEFAULTS)
                    sb.write_file("/tmp/t.py", script.encode()).result()
                    proc = sb.exec(
                        ["python", "/tmp/t.py"], timeout_seconds=10
                    ).result()
                    try:
                        verdict = json.loads(
                            sb.read_file("/tmp/result.json").result().decode()
                        )
                        passed = bool(verdict.get("passed"))
                        error = str(verdict.get("error", ""))
                    except Exception:
                        passed = False
                        error = (proc.stderr or "no result file written")
                    end_time = time.time()
                    return {
                        "passed": passed,
                        "error": error[-300:],
                        "sandbox_latency": (end_time - start_time),
                    }
                except SandboxTimeoutError:
                    # Parent timeout (caught before SandboxError below)
                    end_time = time.time()
                    return {
                        "passed": False,
                        "error": "execution timed out after 10s",
                        "sandbox_latency": (end_time - start_time),
                    }
                except (SandboxExecutionError, SandboxError) as e:
                    last_exc = e
                    time.sleep(2 ** attempt)
                finally:
                    if sb is not None:
                        try:
                            sb.stop(missing_ok=True).result()
                        except Exception:
                            pass
            end_time = time.time()
            return {"passed": False, "error": f"Sandbox unavailable after 3 attempts: {last_exc}", "sandbox_latency": (end_time - start_time)}

    return (CodeScorer,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(f"""
    ---
    ## 4. Benchmark tasks

    /// admonition | Build a versioned Weave Dataset
        type: info

    Pick the problem set the agents solve. Two are wired up behind a small
    `BENCHMARKS` registry (the data sibling of the `AgentBackend` seam):

    - **Built-in demo** — the LeetCode-style easy/medium/hard prompts with
      deterministic `(input, expected)` tuple tests.
    - **HumanEval** — the canonical 164-problem coding benchmark, downloaded on
      demand. Each problem is a function signature + docstring; a hidden
      `check()` program verifies the agent's solution.
    - **MBPP** — the 974-problem "Mostly Basic Python Problems" set. Each problem
      is a short natural-language task; the agent writes the named function and a
      hidden batch of asserts (wrapped as a `check()`) verifies it.

    All are normalized to the same row schema, so the same `predict` and
    `CodeScorer` handle either. The difference from the code-gen tutorial is
    *who* solves them: here a coding agent in a sandbox, not a single API call.
    Choose a benchmark and the tasks to include; the selection builds a
    versioned Weave `Dataset`.
    ///
    """)
    return


@app.cell(hide_code=True)
def _():
    # ---------- 4.1 Ground-truth dataset ----------
    TASKS = [
        # --- Easy ---
        {
            "name": "add",
            "spec": "Write a function `add(a, b)` that returns the sum of two numbers.",
            "tests": [((2, 3), 5), ((-1, 1), 0), ((0, 0), 0)],
        },
        {
            "name": "reverse_string",
            "spec": "Write a function `reverse_string(s)` that returns the reverse of string s.",
            "tests": [(("hello",), "olleh"), (("",), ""), (("a",), "a")],
        },
        {
            "name": "fizzbuzz",
            "spec": "Write a function `fizzbuzz(n)` returning 'Fizz' if n is divisible by 3, 'Buzz' if by 5, 'FizzBuzz' if by both, else str(n).",
            "tests": [((3,), "Fizz"), ((5,), "Buzz"), ((15,), "FizzBuzz"), ((7,), "7")],
        },
        # --- Medium ---
        {
            "name": "is_prime",
            "spec": "Write a function `is_prime(n)` that returns True iff n is a prime number. n is a positive integer.",
            "tests": [((2,), True), ((4,), False), ((17,), True), ((1,), False)],
        },
        {
            "name": "second_largest",
            "spec": "Write a function `second_largest(nums)` returning the second-largest distinct value in a list of ints. Assume len(nums) >= 2 and at least 2 distinct values.",
            "tests": [(([1, 2, 3],), 2), (([5, 5, 4, 4, 3],), 4), (([-1, -2, -3],), -2)],
        },
        {
            "name": "flatten",
            "spec": "Write a function `flatten(lst)` that takes a possibly nested list of ints and returns a flat list of all ints in order.",
            "tests": [
                (([1, [2, [3, 4]], 5],), [1, 2, 3, 4, 5]),
                (([],), []),
                (([[1], [2, [3]]],), [1, 2, 3]),
            ],
        },
        {
            "name": "group_anagrams",
            "spec": "Write a function `group_anagrams(words)` that groups a list of strings into lists of anagrams. Each group must be sorted alphabetically internally. The returned list of groups must be sorted by the first element of each group.",
            "tests": [
                ((["eat", "tea", "tan", "ate", "nat", "bat"],), [["ate", "eat", "tea"], ["bat"], ["nat", "tan"]]),
                (([""],), [[""]]),
                ((["a"],), [["a"]]),
            ],
        },
        {
            "name": "longest_common_subsequence",
            "spec": "Write a function `longest_common_subsequence(s1, s2)` that returns the length of the longest common subsequence of strings s1 and s2.",
            "tests": [
                (("abcde", "ace"), 3),
                (("abc", "abc"), 3),
                (("abc", "def"), 0),
            ],
        },
        # --- Hard ---
        {
            "name": "min_coins",
            "spec": "Write a function `min_coins(coins, amount)` that returns the minimum number of coins needed to make up the given amount using the given coin denominations. Return -1 if it is not possible.",
            "tests": [
                (([1, 5, 11], 15), 3),
                (([2], 3), -1),
                (([1, 2, 5], 11), 3),
            ],
        },
        {
            "name": "longest_palindrome",
            "spec": "Write a function `longest_palindrome(s)` that returns the longest palindromic substring of s. If there are ties, return the one that starts earliest.",
            "tests": [
                (("babad",), "bab"),
                (("cbbd",), "bb"),
                (("a",), "a"),
                (("racecar",), "racecar"),
            ],
        },
        {
            "name": "word_break",
            "spec": "Write a function `word_break(s, word_dict)` that returns True if the string s can be segmented into a space-separated sequence of one or more words from word_dict (a list of strings).",
            "tests": [
                (("leetcode", ["leet", "code"]), True),
                (("applepenapple", ["apple", "pen"]), True),
                (("catsandog", ["cats", "dog", "sand", "and", "cat"]), False),
            ],
        },
    ]
    return (TASKS,)


@app.cell
def _(TASKS):
    # ---------- 4.2 Benchmark loaders ----------
    # Every benchmark, demo or real, is normalized to ONE row schema so the
    # weave.Dataset, predict(), and CodeScorer never have to branch on the source:
    #   name          -> the function the agent must write
    #   spec          -> the problem text shown to the agent (tests stay hidden)
    #   tests         -> [(args, expected), ...] tuple asserts (demo benchmark)
    #   test_program  -> a `def check(candidate): assert ...` program (HumanEval, MBPP)
    #   entry_point   -> the function `check` is called with
    #   source        -> a human label/id for the row (difficulty or task_id)
    # A row uses EITHER `tests` (tuple asserts) OR `test_program` (a check fn);
    # the scorer prefers `test_program` when present.
    import gzip
    import json as _json
    import re as _re
    import urllib.request

    # Official HumanEval problem set (164 problems). /raw/ redirects to
    # raw.githubusercontent.com, which urllib follows automatically.
    HUMANEVAL_URL = (
        "https://github.com/openai/human-eval/raw/master/data/HumanEval.jsonl.gz"
    )
    # MBPP "Mostly Basic Python Problems" (974 problems), one JSON object per line.
    MBPP_URL = (
        "https://github.com/google-research/google-research/raw/master/mbpp/mbpp.jsonl"
    )
    _BENCH_CACHE: dict = {}

    def _difficulty_for(index: int) -> str:
        return "Easy" if index < 3 else "Medium" if index < 8 else "Hard"

    def load_demo(limit: int | None = None) -> list:
        """The 11 hand-written LeetCode-style tasks, normalized to the schema."""
        rows = [
            {
                "name": _t["name"],
                "spec": _t["spec"],
                "tests": _t["tests"],
                "test_program": None,
                "entry_point": _t["name"],
                "source": _difficulty_for(_i),
            }
            for _i, _t in enumerate(TASKS)
        ]
        return rows[:limit] if limit else rows

    def _ssl_context():
        # Standalone/uv-managed interpreters don't always trust the OS keychain,
        # which makes a plain urllib HTTPS GET fail with CERTIFICATE_VERIFY_FAILED.
        # certifi ships transitively with wandb/weave, so use its CA bundle when
        # available and fall back to the default context otherwise.
        import ssl
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:  # noqa: BLE001
            return ssl.create_default_context()

    def load_humaneval(limit: int | None = None) -> list:
        """HumanEval: download + cache the JSONL, map each problem to the schema.
        Runs in the notebook process (which already needs internet), not a sandbox."""
        if "humaneval" not in _BENCH_CACHE:
            _req = urllib.request.Request(
                HUMANEVAL_URL, headers={"User-Agent": "Mozilla/5.0"}
            )
            _raw = urllib.request.urlopen(_req, timeout=60, context=_ssl_context()).read()
            _text = gzip.decompress(_raw).decode()
            _problems = [
                _json.loads(_line) for _line in _text.splitlines() if _line.strip()
            ]
            _BENCH_CACHE["humaneval"] = [
                {
                    "name": _p["entry_point"],
                    "spec": _p["prompt"],
                    "tests": [],
                    "test_program": _p["test"],
                    "entry_point": _p["entry_point"],
                    "source": _p["task_id"],
                }
                for _p in _problems
            ]
        rows = _BENCH_CACHE["humaneval"]
        return rows[:limit] if limit else rows

    def _mbpp_entry_point(code: str, test_list: list) -> str:
        # MBPP `code` may define helper functions/globals before the real one, so
        # pick the def that's actually CALLED in the tests; fall back to the last def.
        defs = _re.findall(r"(?m)^[ \t]*def\s+(\w+)\s*\(", code)
        called = " ".join(test_list)
        for _d in defs:
            if _re.search(rf"\b{_re.escape(_d)}\s*\(", called):
                return _d
        return defs[-1] if defs else "solution"

    def _mbpp_test_program(test_list: list, setup_code: str) -> str:
        # Wrap MBPP's bare assert strings (which reference the function by its real
        # name) in a `check(candidate)` so the SAME scorer path as HumanEval runs
        # them. `candidate` is unused — the asserts hit the global the agent defined.
        body = []
        for _line in (setup_code or "").splitlines():
            body.append(("    " + _line) if _line.strip() else "")
        for _assert in test_list:
            body.extend("    " + _line for _line in _assert.splitlines())
        if not any(_l.strip() for _l in body):
            body = ["    pass"]
        return "def check(candidate):\n" + "\n".join(body) + "\n"

    def load_mbpp(limit: int | None = None) -> list:
        """MBPP: download + cache the JSONL, map each problem to the schema. The
        function name is derived from the reference code; the agent gets only the
        natural-language `text` (tests stay hidden), same as the other benchmarks."""
        if "mbpp" not in _BENCH_CACHE:
            _req = urllib.request.Request(
                MBPP_URL, headers={"User-Agent": "Mozilla/5.0"}
            )
            _text = (
                urllib.request.urlopen(_req, timeout=60, context=_ssl_context())
                .read()
                .decode()
            )
            _problems = [
                _json.loads(_line) for _line in _text.splitlines() if _line.strip()
            ]
            _rows = []
            for _p in _problems:
                _ep = _mbpp_entry_point(_p["code"], _p["test_list"])
                _rows.append(
                    {
                        "name": _ep,
                        "spec": _p["text"],
                        "tests": [],
                        "test_program": _mbpp_test_program(
                            _p["test_list"], _p.get("test_setup_code", "")
                        ),
                        "entry_point": _ep,
                        "source": f"MBPP/{_p['task_id']}",
                    }
                )
            _BENCH_CACHE["mbpp"] = _rows
        rows = _BENCH_CACHE["mbpp"]
        return rows[:limit] if limit else rows

    # Registry mirrors BACKENDS: adding BigCodeBench later is one more entry.
    BENCHMARKS = {
        "demo": {"display": "Built-in demo (11 tasks)", "load": load_demo, "size": 11},
        "humaneval": {"display": "HumanEval (164 problems)", "load": load_humaneval, "size": 164},
        # "mbpp": {"display": "MBPP (974 problems)", "load": load_mbpp, "size": 974},
    }
    return (BENCHMARKS,)


@app.cell(hide_code=True)
def _(BENCHMARKS, mo):
    # ---------- 4.3 Benchmark picker ----------
    benchmark_dropdown = mo.ui.dropdown(
        options={_v["display"]: _k for _k, _v in BENCHMARKS.items()},
        value=BENCHMARKS["humaneval"]["display"],
        label="Benchmark",
    )
    # A benchmark x 4 agents x (agent run + scorer sandbox) is expensive, so cap the
    # count by default; raise it for a fuller run. Stop at the largest benchmark.
    _max_size = max(_v["size"] for _v in BENCHMARKS.values())
    max_problems = mo.ui.number(start=1, stop=_max_size, step=1, value=20, label="Max problems")
    mo.vstack(
        [
            mo.md(
                """
                ### Choose a benchmark

                Pick the problem set the agents will solve. **Built-in demo** is the
                11 hand-written tasks; **HumanEval** (164) and **MBPP** (974) are the
                canonical function-completion benchmarks, downloaded on demand. Use
                **Max problems** to cap how many are loaded — each problem is run by
                every selected agent and scored in its own sandbox, so a full
                benchmark x 4-agent sweep is costly.
                """
            ),
            mo.hstack([benchmark_dropdown, max_problems], justify="start", gap=2),
        ]
    )
    return benchmark_dropdown, max_problems


@app.cell(hide_code=True)
def _(BENCHMARKS, benchmark_dropdown, max_problems, mo):
    # ---------- 4.4 Load the selected benchmark ----------
    benchmark_id = benchmark_dropdown.value or "demo"
    _limit = int(max_problems.value) if max_problems.value else None

    try:
        loaded_tasks = BENCHMARKS[benchmark_id]["load"](_limit)
        _load_error = None
    except Exception as _e:  # noqa: BLE001 — surface as a callout, never crash the notebook
        loaded_tasks = []
        _load_error = f"{type(_e).__name__}: {_e}"

    if _load_error:
        _bench_summary = mo.callout(
            mo.md(
                f"⚠️ Could not load **{BENCHMARKS[benchmark_id]['display']}**: "
                f"`{_load_error}`. Check your machine's internet access and retry."
            ),
            kind="danger",
        )
    else:
        _bench_summary = mo.callout(
            mo.md(
                f"**Benchmark:** `{BENCHMARKS[benchmark_id]['display']}`  \n"
                f"**Loaded problems:** `{len(loaded_tasks)}` "
                f"(of `{BENCHMARKS[benchmark_id]['size']}` available)"
            ),
            kind="success",
        )
    _bench_summary
    return benchmark_id, loaded_tasks


@app.cell(hide_code=True)
def _(loaded_tasks, mo):
    _all_task_rows = [
        {
            "#": _i,
            "source": _t["source"],
            "function": _t["name"],
            "checks": "check()" if _t.get("test_program") else f"{len(_t['tests'])} asserts",
            "spec": (_t["spec"][:120] + "…") if len(_t["spec"]) > 120 else _t["spec"],
        }
        for _i, _t in enumerate(loaded_tasks)
    ]
    task_table = mo.ui.table(
        _all_task_rows,
        selection="multi",
        initial_selection=list(range(len(_all_task_rows))),
        label="Select the benchmark tasks to include in this evaluation",
        page_size=20,
    )
    task_table
    return (task_table,)


@app.cell(hide_code=True)
def _(benchmark_id, loaded_tasks, mo, task_table, weave):
    # Map the selected table rows back to their full schema dicts by index.
    _selected_idx = sorted(
        _row["#"] for _row in (task_table.value or []) if "#" in _row
    )
    selected_benchmark_tasks = [loaded_tasks[_i] for _i in _selected_idx]

    dataset_name = f"{benchmark_id}_{len(selected_benchmark_tasks)}tasks"

    dataset = (
        weave.Dataset(name=dataset_name, rows=selected_benchmark_tasks)
        if selected_benchmark_tasks
        else None
    )

    if selected_benchmark_tasks:
        _summary = mo.callout(
            mo.md(
                f"**Weave dataset:** `{dataset_name}`  \n"
                f"**Selected tasks:** `{len(selected_benchmark_tasks)}` of "
                f"`{len(loaded_tasks)}` loaded"
            ),
            kind="success",
        )
    else:
        _summary = mo.callout(
            mo.md("No tasks selected — check one or more rows in the table above to build a dataset."),
            kind="warn",
        )
    _summary
    return dataset, dataset_name, selected_benchmark_tasks


@app.cell(hide_code=True)
def _(mo):
    mo.md(f"""
    ---
    ## 5. Pick agents and launch an evaluation

    /// admonition | Run a per-agent weave.Evaluation
        type: info

    Choose the agent(s) to evaluate, then press **Run selected evaluation**. Each
    selected agent is wrapped in a `SandboxAgentModel`, which provisions its own
    sandbox (install + auth) before the run, solves every task inside that
    sandbox, and is scored by `CodeScorer`. Results are logged as a
    `weave.Evaluation` per agent. Agent sandboxes are torn down when the run
    completes.

    An agent is only runnable if its provider key was entered in the Connect
    form, rows without a key are flagged below.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(BACKENDS, PROVIDER_KEYS, mo):
    _agent_rows = [
        {
            "agent_id": _b.id,
            "agent": _b.display_name,
            "provider": _b.provider,
            "key_status": "✅ provided" if PROVIDER_KEYS.get(_b.key_field) else "❌ missing",
        }
        for _b in BACKENDS.values()
    ]
    agent_table = mo.ui.table(
        _agent_rows,
        selection="multi",
        initial_selection=[_i for _i, _r in enumerate(_agent_rows) if _r["key_status"].startswith("✅")],
        label="Select the coding agents to evaluate",
        page_size=20,
    )
    run_eval_button = mo.ui.run_button(
        label="Run selected evaluation",
        tooltip="Provision a sandbox per agent, solve tasks inside it, score in Weave.",
        kind="success",
    )
    model_picker_modal = mo.vstack(
        [
            mo.md(
                """
                ### Evaluation controls

                Check the agents you want to evaluate, then click **Run selected
                evaluation**. Agents whose provider key is missing will be skipped.
                """
            ),
            agent_table,
            run_eval_button,
        ]
    )

    model_picker_modal
    return agent_table, run_eval_button


@app.cell(hide_code=True)
def _(agent_table, mo):
    selected_agent_ids = [
        _row["agent_id"] for _row in (agent_table.value or []) if _row.get("agent_id")
    ]
    _label = ", ".join(selected_agent_ids) if selected_agent_ids else "No agents selected"

    mo.md(
        f"""
        **Selected agent(s):** `{_label}`  
        **Number of agent runs queued:** `{len(selected_agent_ids)}`
        """
    )
    return (selected_agent_ids,)


@app.cell(hide_code=True)
async def _(
    BACKENDS,
    CodeScorer,
    PROVIDER_KEYS,
    SandboxAgentModel,
    dataset,
    dataset_name,
    mo,
    run_eval_button,
    selected_agent_ids,
    selected_benchmark_tasks,
    weave,
):
    import os as _os

    # Weave evaluates rows concurrently (WEAVE_PARALLELISM). Unlike a hosted-API
    # eval, here every concurrent predict is a FULL agent process (Node/Rust) sharing
    # ONE agent sandbox, so the old default of 20 starved CPU/RAM and OOM-killed
    # agents — surfacing as empty-output runs and 180s timeouts (notably Claude).
    # Cap the default at a sandbox-friendly 4; raise WEAVE_PARALLELISM if your agent
    # sandbox has more headroom. Harness agents still pin eval_parallelism=1 (shared
    # per-sandbox state deadlocks). We set this PER AGENT right before evaluate().
    _DEFAULT_PARALLELISM = _os.environ.get("WEAVE_PARALLELISM", "4")

    async def _run_evaluations():
        _lines = []
        _created = []
        try:
            for _agent_id in selected_agent_ids:
                _backend = BACKENDS[_agent_id]
                _key = PROVIDER_KEYS.get(_backend.key_field)
                if not _key:
                    _lines.append(f"⚠️ Skipped **{_backend.display_name}** — missing `{_backend.key_field}`.")
                    continue

                _model = SandboxAgentModel(agent_id=_agent_id)
                _model._api_key = _key

                # Per-task budget: harness agents (OpenClaw) override the default.
                if _backend.run_timeout_seconds:
                    _model.run_timeout_seconds = _backend.run_timeout_seconds
                # Sandbox lifetime must outlast the WHOLE eval. Parallel agents finish
                # fast, but serial agents (eval_parallelism=1) run tasks back-to-back,
                # so a fixed cap expires mid-eval and the sandbox vanishes (NOT_FOUND).
                # Scale the lifetime by task count for those, keeping the default floor.
                if _backend.eval_parallelism == 1:
                    _per_task = _model.run_timeout_seconds + 60  # + scorer/overhead
                    _model.max_lifetime_seconds = max(
                        _model.max_lifetime_seconds,
                        _model.install_timeout_seconds
                        + len(selected_benchmark_tasks) * _per_task,
                    )

                _created.append(_model)
                # Provision now (traced via the agent_setup op) so install errors
                # surface here and don't skew the first row's latency. setup() returns
                # a status dict instead of raising.
                _setup = _model.ensure_ready()
                if _setup.get("status") != "ready":
                    _lines.append(
                        f"❌ **{_backend.display_name}** setup failed: {_setup.get('error')}"
                    )
                    continue
                _lines.append(
                    f"🟢 **{_backend.display_name}** sandbox `{_setup.get('sandbox_id')}` ready."
                )

                # Pin concurrency for this agent (harness agents -> 1).
                _par = _backend.eval_parallelism
                _os.environ["WEAVE_PARALLELISM"] = str(_par) if _par else _DEFAULT_PARALLELISM
                _lines.append(
                    f"&nbsp;&nbsp;↳ concurrency `{_os.environ['WEAVE_PARALLELISM']}`, "
                    f"per-task timeout `{_model.run_timeout_seconds}s`, "
                    f"sandbox lifetime `{_model.max_lifetime_seconds}s`."
                )

                _scorer = CodeScorer(name="code_scorer")
                _evaluation = weave.Evaluation(
                    name="agent-code-eval",
                    dataset=dataset,
                    scorers=[_scorer],
                    evaluation_name=f"{_agent_id}_agent_eval",
                )
                _results = await _evaluation.evaluate(model=_model)
                print(f"Agent: {_agent_id}")
                print(_results)
                print("-" * 100)
                _lines.append(f"✅ **{_backend.display_name}** evaluation finished.")
        finally:
            for _m in _created:
                _m.stop()
        return _lines

    if run_eval_button.value and selected_agent_ids and selected_benchmark_tasks:
        _out_lines = await _run_evaluations()
        _evaluation_status = mo.md(
            "### Run summary\n\n" + "\n\n".join(_out_lines) +
            f"\n\nDataset **`{dataset_name}`**. Open W&B Weave to inspect traces and metrics."
        )
    elif run_eval_button.value and not selected_agent_ids:
        _evaluation_status = mo.md("⚠️ No agents selected. Pick at least one agent above, then run again.")
    elif run_eval_button.value and not selected_benchmark_tasks:
        _evaluation_status = mo.md("⚠️ No benchmark tasks selected. Pick at least one task above, then run again.")
    else:
        _evaluation_status = mo.md(
            "⏸️ Evaluation is ready but has not been launched. Choose agents and tasks, then click **Run selected evaluation**."
        )

    _evaluation_status
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 6. Lifecycle, discovery, and cleanup

    /// admonition | Find and stop sandboxes
        type: info

    Both agent and scorer sandboxes are tagged `agent-sandbox-eval`. The run loop
    tears down agent sandboxes automatically, but if a run is interrupted you can
    discover and stop any survivors with `Sandbox.list` + `stop`.

    ```python
    running = Sandbox.list(tags=["agent-sandbox-eval"], include_stopped=True).result()
    sb = Sandbox.from_id(running[0].sandbox_id).result()
    print(sb.get_status())
    sb.stop(missing_ok=True).result()
    ```
    ///
    """)
    return


@app.cell
def _(mo):
    lifecycle_btn = mo.ui.run_button(label="List my agent-eval sandboxes", kind="neutral")
    lifecycle_btn
    return (lifecycle_btn,)


@app.cell(hide_code=True)
def _(API_KEY, Sandbox, lifecycle_btn, mo):
    mo.stop(not API_KEY, mo.md("_Connect at the top first._"))
    mo.stop(not lifecycle_btn.value, mo.md("_Press the button to list tagged sandboxes._"))

    try:
        _sandboxes = Sandbox.list(
            tags=["agent-sandbox-eval"], include_stopped=True
        ).result()
        _rows = [
            f"- `{_s.sandbox_id}` — status `{_s.status}`"
            for _s in _sandboxes[:20]
        ]
        _body = "\n".join(_rows) or "_No tagged sandboxes yet — run an evaluation above first._"
        _out = mo.callout(
            mo.md(
                f"**Sandboxes tagged `agent-sandbox-eval`:** {len(_sandboxes)}\n\n{_body}"
            ),
            kind="success",
        )
    except Exception as _e:
        _out = mo.callout(
            mo.md(f"⚠️ Listing unavailable here: `{type(_e).__name__}: {_e}`"),
            kind="warn",
        )
    _out
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## What you just did

    /// admonition | Recap
        type: success

    - Connected to W&B and supplied provider keys for headless agent auth
    - Defined coding agents (Codex, Claude, OpenClaw, Hermes) behind an `AgentBackend` seam
    - Wrapped each agent in a `SandboxAgentModel` that **provisions a sandbox at
      init**, installs + authenticates the CLI, and drives it inside the sandbox
      on every `predict`
    - `CodeScorer` to verify solutions in fresh, network-isolated sandboxes
    - Ran a per-agent `weave.Evaluation` and traced every generation + score
    - Tore down agent sandboxes and listed survivors for cleanup
    ///

    /// details | Where to next
        type: info

    - [Serverless Sandboxes docs](https://docs.wandb.ai/sandboxes)
    - [W&B Weave docs](https://weave-docs.wandb.ai/)
    ///
    """)
    return


if __name__ == "__main__":
    app.run()
