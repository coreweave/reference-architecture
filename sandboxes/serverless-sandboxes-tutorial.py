# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "cwsandbox==0.24.0",
#     "marimo>=0.23.8",
#     "openai==2.46.0",
#     "wandb[sandbox]==0.27.0",
#     "weave==0.52.38",
# ]
# ///

import marimo

__generated_with = "0.23.6"
app = marimo.App(
    width="medium",
    app_title="Serverless Sandbox Tutorial",
    css_file="/usr/local/_marimo/custom.css",
    auto_download=["html"],
)


@app.cell
def _():
    import os
    import time
    import weave
    import openai
    import marimo as mo
    from wandb.sandbox import (
        Sandbox,
        SandboxDefaults,
        ResourceOptions,
        SandboxCommandTimeoutError,
        SandboxExecutionError,
        SandboxError,
    )

    return (
        ResourceOptions,
        Sandbox,
        SandboxCommandTimeoutError,
        SandboxDefaults,
        SandboxError,
        SandboxExecutionError,
        mo,
        openai,
        os,
        time,
        weave,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                r"""
                # Evaluating Code-Generation Models with Serverless Sandbox, Inference, and Weave

                /// admonition | About This Notebook
                    type: info

                This marimo notebook walks through an end-to-end code-evaluation workflow for
                hosted LLMs. It uses three complementary products:

                - **Serverless Inference** to call hosted code-generation models through an OpenAI-compatible API.
                - **Serverless Sandbox** to execute generated Python safely in isolated environments.
                - **W&B Weave** to trace model calls, score outputs, and compare evaluation runs.

                The flow is: a model generates a Python function for each benchmark task, the
                function runs against deterministic tests inside a sandbox, the pass/fail result
                becomes a score, and every step is traced to Weave for side-by-side comparison.

                _If you are running this notebook in edit mode, make sure you start by running all cells._
                ///
                """
            ),
            mo.md(
                r"""
                /// details | Prerequisites
                    type: info

                Before you begin, make sure you have:

                - **A W&B account** — sign up free at [wandb.ai](https://wandb.ai) if you don't have one.
                - **A W&B API key** *(required)* — generate one at [wandb.ai/authorize](https://wandb.ai/authorize) and paste it into the Connect form below. It authenticates both Inference and Weave logging.
                - **Inference access** — needed to call the hosted models in the picker. See [Serverless Inference](https://docs.wandb.ai/guides/inference/).

                Use the controls below to connect, choose benchmark difficulties, select one or
                more models, and launch a reproducible evaluation run.
                ///
                """
            ),
            mo.md(
                r"""
                /// details | Table of Contents
                    type: info

                - [**Connect W&B services**](#1-connect-wb-services) - Authenticate and initialize Weave
                - [**Define the code-generation agent**](#2-define-the-code-generation-agent) - Wrap a hosted model as a Weave `Model`
                - [**Score generated code safely in Serverless Sandbox**](#3-score-generated-code-safely-in-serverless-sandbox) - Run untrusted code in isolation
                - [**Benchmark tasks**](#4-benchmark-tasks) - Build a versioned Weave `Dataset`
                - [**Pick models and launch an evaluation**](#5-pick-models-and-launch-an-evaluation) - Run a multi-model `weave.Evaluation`
                - [**Lifecycle, discovery, and cleanup**](#6-lifecycle-discovery-and-cleanup) - Find and stop sandboxes
                ///
                """
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(f"""
    ---
    ## 1. Connect W&B services

    /// admonition | Connect and initialize Weave
        type: info

    Fill in the **Connect** form above with your W&B entity (team or username),
    a project name, and your API key, then press **Connect**. The entity and
    project default to the tutorial values: change them to log into your own
    workspace. The key is stored in `WANDB_API_KEY` and used to call
    `weave.init("<entity>/<project>")`.

    The form gates the rest of the notebook: the agent, scorer, and evaluation
    cells stay paused until you connect. Once connected, every model call,
    generated solution, scorer result, and evaluation summary is logged under
    your project, and a link to the Weave dashboard appears in the success
    callout above.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    # ---------- 1. Setup W&B ----------
    wandb_connect_form = (
        mo.md("""
        - W&B entity *(team)*: {entity}
        - W&B project: {project}
        - W&B API key *(required)*: {api_key}
        """)
        .batch(
            entity=mo.ui.text(placeholder="your-wandb-entity" , full_width=True),
            project=mo.ui.text(value="serverless-sandbox-tutorial", full_width=True),
            api_key=mo.ui.text(kind="password", placeholder="from wandb.ai/authorize", full_width=True),
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
        mo.md("_Fill in the form above and press **Connect**._"),
    )

    os.environ["WANDB_API_KEY"] = API_KEY
    weave.init(f"{ENTITY}/{PROJECT}")
    weave_url = f"https://wandb.ai/{ENTITY}/{PROJECT}/weave"

    mo.callout(
        mo.md(
            f"✅ **Connected** — logging to `{ENTITY}/{PROJECT}`. "
            f"[Open Weave dashboard]({weave_url})"
        ),
        kind="success",
    )
    return API_KEY, ENTITY, PROJECT


@app.cell(hide_code=True)
def _(mo):
    wandb_product_tabs = mo.ui.tabs(
        {
            "Sandbox": mo.md(
                f"""
                ### Serverless Sandbox

                The sandbox executes each generated Python solution in an isolated environment. This keeps evaluation safer while still letting the scorer run real assertions against generated code.

                It's a full remote-execution platform: file I/O (`write_file`/`read_file`), CPU/memory resource control, env vars and team Secrets, networking/egress, live log streaming, parallel `Session`s with remote functions, and tag-based lifecycle management. Serverless Sandbox runs CPU workloads (no GPU). The code scorer in Step 3 exercises these directly.
                """
            ),
            "Inference": mo.md(
                f"""
                ### Serverless Inference

                This notebook uses Serverless Inference through an OpenAI-compatible client. Each benchmark prompt is sent to a hosted model with a low-temperature generation setting so the evaluation is repeatable and easy to compare across model providers.
                """
            ),
            "Weave": mo.md(
                f"""
                ### W&B Weave

                Weave tracks the full evaluation lifecycle: model inputs, generated code, scorer outputs, pass/fail metrics, and latency. That makes it easy to inspect individual failures and compare runs across models.
                """
            )
        }
    )

    wandb_product_tabs
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(f"""
    ---
    ## 2. Define the code-generation agent

    /// admonition | LeetCodeAgent
        type: info

    `LeetCodeAgent` wraps a Serverless Inference model behind a Weave `Model` interface. Given a task name, spec, and tests, its `predict` method returns the model's raw solution string, the output drops straight into the sandbox scorer. `predict` is a `@weave.op`, so each
    generation is traced with its inputs, output, and latency.
    ///
    """)
    return


@app.cell
def _(API_KEY, ENTITY, PROJECT, openai, weave):
    #---------- 1.1 Define Function Agent ----------
    SYSTEM_PROMPT = weave.StringPrompt(
        """You are a precise Python coder.
        Given a function specification, return ONLY the function definition.
        - No markdown code fences.
        - No explanation.
        - Use the exact function name and signature requested.
        """
    )
    class LeetCodeAgent(weave.Model):
        model_name: str
        system_prompt: weave.StringPrompt = SYSTEM_PROMPT
        max_tokens: int = 1000
        temperature: float = 0.0

        @property
        def client(self):
            return openai.OpenAI(
                base_url="https://api.inference.wandb.ai/v1",
                api_key=API_KEY,
                project=f"{ENTITY}/{PROJECT}",
            )

        @weave.op(name="generate_solution", kind="llm")
        def predict(self, name: str, spec: str, tests: list) -> str:
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT.content},
                    {"role": "user", "content": spec},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            msg = resp.choices[0].message

            # Standard content
            if msg.content:
                return msg.content.strip()

            # Reasoning/thinking models (e.g. Qwen, DeepSeek-R1) that put output in reasoning_content
            reasoning = getattr(msg, "reasoning_content", None)
            if reasoning:
                return reasoning.strip()

            # Tool-call responses — extract the first tool call argument
            if msg.tool_calls:
                return msg.tool_calls[0].function.arguments.strip()

            return "failed"

    return (LeetCodeAgent,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 3. Score generated code safely in Serverless Sandbox

    /// admonition | CodeScorer
        type: info

    `CodeScorer` is where the sandbox does its real work. It wraps each task's
    `(input, expected)` pairs in a small harness, runs the model's solution inside
    a fresh sandbox, and returns a structured `{passed, error, sandbox_latency}`
    result for Weave. Running untrusted model output in an isolated sandbox is the
    whole point so the evaluation stays safe.

    The scorer sets these Sandbox defaults:

    - **`SandboxDefaults`** (defined just below) — one immutable config applied to
      every scorer sandbox: container image, `tags` (used for cleanup in the final
      step), injected **environment variables**, and **CPU/memory `ResourceOptions`**.
    - **`write_file` + `read_file`** — the harness script is written in with
      `write_file`; instead of scraping stdout, the script writes a JSON verdict to
      `/tmp/result.json` that the scorer pulls back with `read_file`.
    - **Native `timeout_seconds`** — the SDK enforces the 5s budget directly, so
      there's no `timeout 5` shell wrapper.
    - **Network isolation by default** — sandboxes have no egress unless you ask
      for it, so model code can't phone home while being scored.
    - **Typed errors** — `SandboxCommandTimeoutError` is a *real* failed completion
      (no retry); `SandboxExecutionError` / `SandboxError` are infra issues the
      backoff loop retries.
    ///
    """)
    return


@app.cell
def _(ResourceOptions, SandboxDefaults):
    # Shared sandbox configuration. SandboxDefaults is an immutable config object
    # applied to every sandbox the scorer creates — container image, tags (for
    # later discovery/cleanup via Sandbox.list), injected env vars, and CPU/memory
    # limits. Setting it once here is the idiomatic alternative to passing the same
    # arguments on every Sandbox.run() call.
    SANDBOX_DEFAULTS = SandboxDefaults(
        container_image="python:3.11",
        tags=("wandb-sandbox-tutorial", "code-eval"),
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
    SandboxCommandTimeoutError,
    SandboxError,
    SandboxExecutionError,
    time,
    weave,
):
    # ---------- 1.3 Define Sandbox-based scorer ----------
    import json

    class CodeScorer(weave.Scorer):

        @weave.op(name="code_scorer", kind="scorer")
        def score(self, name: str, spec: str, tests: list, output: str) -> dict:
            start_time = time.time()
            asserts = "\n".join(
                f"    assert {name}(*{args!r}) == {expected!r}, 'failed on input {args!r}'"
                for args, expected in tests
            )
            # The harness runs every assertion, then writes a structured verdict
            # to a file, which we pull back out with read_file.
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
                    # write_file ships the script in; 
                    # read_file pulls the verdict back out
                    sb.write_file("/tmp/t.py", script.encode()).result()
                    proc = sb.exec(
                        ["python", "/tmp/t.py"], timeout_seconds=5
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
                except SandboxCommandTimeoutError:
                    end_time = time.time()
                    return {
                        "passed": False,
                        "error": "execution timed out after 5s",
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
    mo.md(r"""
    /// details | Also possible (beyond this eval)
        type: info

    A few sandbox capabilities aren't needed to score code, but are one argument
    away when your use case calls for them:

    - **Team Secrets** — inject credentials from your W&B `wandb-team-secrets`
      store without hardcoding them: `Sandbox.run(..., secrets=[Secret(name="OPENAI_API_KEY", env_var="OPENAI_API_KEY")])`.
    - **Outbound egress / serving a port** — the scorer keeps sandboxes isolated,
      but a task that needs the network can opt in:
      `Sandbox.run(..., network=NetworkOptions(egress_mode="internet"))`, or expose
      a port with `ingress_mode` + `exposed_ports` to serve a model.
    - **Live log streaming** — for long-running jobs, follow output as it happens
      with `for line in sb.stream_logs(follow=True): ...`.
    - **Snapshots & lifetime caps** — `sb.stop(snapshot_on_stop=True)` or
      `Sandbox.run(..., max_lifetime_seconds=300)` to bound resource usage.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(f"""
    ---
    ## 4. Benchmark tasks

    /// admonition | Build a versioned Weave Dataset
        type: info

    The benchmark mixes easy, medium, and hard LeetCode-style prompts. Each row
    has a function name, a natural-language spec, and deterministic
    `(input, expected)` tests that the sandbox scorer converts into Python
    assertions. Select the exact tasks you want in the table below, the
    selection updates live and builds a versioned `Dataset` in Weave, so each evaluation run
    is tied to an explicit set of tasks.
    ///
    """)
    return


@app.cell(hide_code=True)
def _():
    # ---------- 1.2 Define Ground truth Dataset ----------
    # Each task has a name, a natural-language spec, and a list of (input, expected) pairs.
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
        {
            "name": "serialize_tree",
            "spec": """Write a function `serialize_tree(root)` that serializes a binary tree to a string and a function `deserialize_tree(data)` that deserializes it back. A tree node is represented as a list [val, left, right] where left and right are either None or another such list. The round-trip must be lossless: deserialize_tree(serialize_tree(root)) == root.""",
            "tests": [
                (([1, [2, None, None], [3, [4, None, None], [5, None, None]]],), [1, [2, None, None], [3, [4, None, None], [5, None, None]]]),
                ((None,), None),
                (([1, None, [2, None, [3, None, None]]],), [1, None, [2, None, [3, None, None]]]),
            ],
        },
    ]
    return (TASKS,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Check the rows you want below. By default every task is selected; uncheck
    any you want to exclude, or clear them all and pick a focused subset. The
    dataset summary underneath updates as you change the selection.
    """)
    return


@app.cell(hide_code=True)
def _(TASKS, mo):
    def _difficulty_for(index: int) -> str:
        return "Easy" if index < 3 else "Medium" if index < 8 else "Hard"

    _all_task_rows = [
        {
            "difficulty": _difficulty_for(_i),
            "function": _t["name"],
            "test_count": len(_t["tests"]),
            "spec": _t["spec"],
        }
        for _i, _t in enumerate(TASKS)
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
def _(TASKS, mo, task_table, weave):
    def _difficulty_for(index: int) -> str:
        return "Easy" if index < 3 else "Medium" if index < 8 else "Hard"

    _difficulty_order = ["Easy", "Medium", "Hard"]
    _task_by_name = {_t["name"]: (_i, _t) for _i, _t in enumerate(TASKS)}

    _selected = sorted(
        (
            _task_by_name[_row["function"]]
            for _row in (task_table.value or [])
            if _row.get("function") in _task_by_name
        ),
        key=lambda _pair: _pair[0],
    )
    selected_benchmark_tasks = [_task for _, _task in _selected]
    _present = [
        _d for _d in _difficulty_order
        if _d in {_difficulty_for(_i) for _i, _ in _selected}
    ]

    if not selected_benchmark_tasks:
        _suffix = "none"
    elif len(selected_benchmark_tasks) == len(TASKS):
        _suffix = "all"
    else:
        _suffix = "_".join(_d.lower() for _d in _present) + f"_{len(selected_benchmark_tasks)}tasks"
    dataset_name = f"tasks_{_suffix}"

    dataset = (
        weave.Dataset(name=dataset_name, rows=selected_benchmark_tasks)
        if selected_benchmark_tasks
        else None
    )

    if selected_benchmark_tasks:
        _summary = mo.callout(
            mo.md(
                f"**Weave dataset:** `{dataset_name}`  \n"
                f"**Selected tasks:** `{len(selected_benchmark_tasks)}` of `{len(TASKS)}` "
                f"({', '.join(_present)})"
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
    ## 5. Pick models and launch an evaluation

    /// admonition | Run a multi-model weave.Evaluation
        type: info

    Pick one hosted model for a fast debug run or the full set for a side-by-side
    comparison, then press **Run selected evaluation**. The run button keeps
    expensive model calls from firing automatically whenever you open or edit the
    notebook. Each selected model is wrapped in a `LeetCodeAgent`, scored by
    `CodeScorer` against the dataset, and logged as a `weave.Evaluation` you can
    open in the Weave dashboard.

    **Parallel sandboxes:** `weave.Evaluation` scores dataset rows
    concurrently, and since `CodeScorer` spins up a sandbox per call, you're
    running many sandboxes in parallel. If you ever own the loop yourself
    (RL rollouts, a custom harness), a `Session` gives you the same fan-out
    explicitly —> `@session.function()` + `.map()` to launch, and
    `wandb.sandbox.wait(refs, num_returns=1)` to harvest results as they finish.
    ///
    """)
    return


@app.cell
def _():
    models_list = [
        "meta-llama/Llama-3.3-70B-Instruct",
        "deepseek-ai/DeepSeek-V4-Flash",
        "MiniMaxAI/MiniMax-M2.5",
        "moonshotai/Kimi-K2.6",
        "Qwen/Qwen3-Coder-480B-A35B-Instruct",

    ]
    return (models_list,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Check rows in the table below to choose between a full model comparison and a single-model debug run.
    """)
    return


@app.cell(hide_code=True)
def _(mo, models_list):
    _model_rows = [
        {"provider": _m.split("/")[0], "model": _m}
        for _m in models_list
    ]
    model_table = mo.ui.table(
        _model_rows,
        selection="multi",
        initial_selection=list(range(len(_model_rows))),
        label="Select the Serverless Inference models to evaluate",
        page_size=20,
    )
    run_eval_button = mo.ui.run_button(
        label="Run selected evaluation",
        tooltip="Run the selected Serverless Inference model(s), score generated code in Sandbox, and log results to Weave.",
        kind="success",
    )
    model_picker_modal = mo.vstack(
        [
            mo.md(
                f"""
                ### Evaluation controls

                Check the models you want to evaluate, then click **Run selected evaluation**. Select a single row for a fast debug run, or all rows for a full side-by-side comparison.
                """
            ),
            model_table,
            run_eval_button,
        ]
    )

    model_picker_modal
    return model_table, run_eval_button


@app.cell(hide_code=True)
def _(mo, model_table):
    selected_model_names = [
        _row["model"] for _row in (model_table.value or []) if _row.get("model")
    ]
    _selected_model_label = ", ".join(selected_model_names) if selected_model_names else "No models selected"

    mo.md(
        f"""
        **Selected evaluation target(s):** `{_selected_model_label}`  
        **Number of model runs queued:** `{len(selected_model_names)}`
        """
    )
    return (selected_model_names,)


@app.cell(hide_code=True)
async def _(
    CodeScorer,
    LeetCodeAgent,
    dataset,
    dataset_name,
    mo,
    run_eval_button,
    selected_benchmark_tasks,
    selected_model_names,
    weave,
):
    async def _run_evaluations():
        for name in selected_model_names:
            _model = LeetCodeAgent(model_name=name)
            _code_scorer = CodeScorer(name="code_scorer")
            evaluation = weave.Evaluation(
                name="simple-code-eval",
                dataset=dataset,
                scorers=[_code_scorer],
                evaluation_name=f"{name}_code_eval",
            )
            results = await evaluation.evaluate(model=_model)
            print(f"Model: {name}")
            print(results)
            print("-" * 100)

    if run_eval_button.value and selected_model_names and selected_benchmark_tasks:
        await _run_evaluations()
        _evaluation_status = mo.md(
            f"""
            ✅ Evaluation finished for **{len(selected_model_names)}** model run(s) on dataset **`{dataset_name}`**. Open W&B Weave to inspect traces, scorer outputs, and aggregate metrics.
            """
        )
    elif run_eval_button.value and not selected_model_names:
        _evaluation_status = mo.md(
            f"""
            ⚠️ No models selected. Pick at least one model above, then click **Run selected evaluation** again.
            """
        )
    elif run_eval_button.value and not selected_benchmark_tasks:
        _evaluation_status = mo.md(
            f"""
            ⚠️ No benchmark tasks selected. Pick at least one difficulty above, then click **Run selected evaluation** again.
            """
        )
    else:
        _evaluation_status = mo.md(
            f"""
            ⏸️ Evaluation is ready but has not been launched. Choose one or more models and benchmark difficulties, then click **Run selected evaluation**.
            """
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

    Sandboxes are addressable resources. `tags` (set via `SandboxDefaults`) let
    you find them later with `Sandbox.list`; `from_id` re-attaches to a running
    one; `get_status` inspects state; and `stop` can snapshot or you can set a
    hard `max_lifetime_seconds` so nothing leaks.

    ```python
    running = Sandbox.list(tags=["wandb-sandbox-tutorial"], include_stopped=True).result()
    sb = Sandbox.from_id(running[0].sandbox_id).result()
    print(sb.get_status())
    sb.stop(snapshot_on_stop=True).result()           # or Sandbox.run(..., max_lifetime_seconds=300)
    ```
    ///
    """)
    return


@app.cell
def _(mo):
    lifecycle_btn = mo.ui.run_button(label="List my tutorial sandboxes", kind="neutral")
    lifecycle_btn
    return (lifecycle_btn,)


@app.cell(hide_code=True)
def _(API_KEY, Sandbox, lifecycle_btn, mo):
    mo.stop(not API_KEY, mo.md("_Connect at the top first._"))
    mo.stop(not lifecycle_btn.value, mo.md("_Press the button to list tagged sandboxes._"))

    import traceback as _tb

    try:
        _sandboxes = Sandbox.list(
            tags=["wandb-sandbox-tutorial"], include_stopped=True
        ).result()
        _rows = [
            f"- `{_s.sandbox_id}` — status `{_s.status}`"
            for _s in _sandboxes[:20]
        ]
        _body = "\n".join(_rows) or "_No tagged sandboxes yet — run the evaluation above first._"
        _out = mo.callout(
            mo.md(
                f"**Sandboxes tagged `wandb-sandbox-tutorial`:** {len(_sandboxes)}\n\n{_body}"
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

    - Connected to W&B from a single form (entity, project, API key)
    - Wrapped a hosted Serverless Inference model in a Weave `Model`
    - Scored generated code safely inside Serverless Sandbox using
      `SandboxDefaults`, `write_file`, native `timeout_seconds`, and typed errors
    - Built a versioned Weave `Dataset` from a selectable task table
    - Ran a multi-model `weave.Evaluation` and logged every trace, Weave scored
      rows concurrently, so sandboxes ran in parallel
    - Exercised the sandbox platform inside the scorer: `SandboxDefaults`, file
      I/O (`write_file`/`read_file`), CPU/memory limits, network isolation, and
      typed errors, then listed the tagged sandboxes for cleanup
    ///

    /// details | Where to next
        type: info

    - [Serverless Sandboxes docs](https://docs.wandb.ai/sandboxes)
    - [Weave docs](https://weave-docs.wandb.ai/)
    - [Weave Evaluations guide](https://weave-docs.wandb.ai/guides/core-types/evaluations)
    ///
    """)
    return


if __name__ == "__main__":
    app.run()
