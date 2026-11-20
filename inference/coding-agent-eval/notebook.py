# ruff: noqa: E501  (long lines are markdown prose)
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "altair>=5.4.0",
#     "anthropic>=2.10.0",
#     "marimo>=0.23.6",
#     "openai>=3.0.0",
#     "pandas>=2.2.0",
#     "weave>=0.54.0",
# ]
# ///

import marimo

__generated_with = "0.23.6"
app = marimo.App(width="medium", app_title="Coding Agent Eval")

with app.setup:
    import os

    import altair as alt
    import marimo as mo
    import pandas as pd
    from coding_eval import (
        DEFAULT_LINEUP,
        PRESETS,
        SI_BASE_URL,
        CompletionJudge,
        ModelSpec,
        build_tasks,
        run_probe,
        summarize_probe,
    )
    from coding_eval.evaluate import collect_rows, escalation_ladder, estimate_requests, leaderboard, run_suite
    from coding_eval.probe import PROBES

    def _open_judge(model_key: str):
        spec = PRESETS[model_key]
        return lambda si_project: CompletionJudge(
            judge_model=spec.model,
            judge_provider="openai",
            judge_base_url=SI_BASE_URL,
            judge_project=si_project,
            judge_input_price=spec.input_price or 0.0,
            judge_output_price=spec.output_price or 0.0,
        )

    # The judge must not be one of the candidates. DeepSeek V4 Pro on Serverless Inference needs
    # no extra key; Claude needs ANTHROPIC_API_KEY.
    JUDGES = {
        "DeepSeek V4 Pro (Serverless Inference)": _open_judge("deepseek-v4-pro"),
        "Claude Opus 5.5 (Anthropic API)": lambda _p: CompletionJudge(judge_model="claude-opus-5-5"),
        "Claude Sonnet 5.5 (Anthropic API)": lambda _p: CompletionJudge(judge_model="claude-sonnet-5-5"),
    }


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # Choosing an Open Model for Your Coding Agent

    This notebook is the companion to the CoreWeave blog post **Choosing an Open Model for your Coding Agent**.
    It builds an evaluation from **your own merged pull requests**, runs three or four open models and your current
    closed model on each task several times, has a frontier model grade every attempt against the code your team
    actually merged, and tracks everything in **W&B Weave**.

    You will come away with each model's **completion rate**, **tool-call accuracy**, **speed**, and
    **cost per successful task**, measured on your code rather than a public benchmark.

    /// details | Contents
        type: info

    1. [**Connect**](#connect): API keys for inference, the judge, and Weave
    2. [**Build Your Task Set**](#build-your-task-set): turn merged PRs into replayable tasks
    3. [**Choose Models**](#choose-models): open candidates plus your closed baseline
    4. [**Probe Tool Calls**](#probe-tool-calls): one-minute check that tool calls survive serving
    5. [**Run the Evaluation**](#run-the-evaluation): models x tasks x trials, graded, in Weave
    6. [**Results**](#results): completion, tool calls, speed, cost per success
    7. [**Use the Winner**](#use-the-winner): point your coding harness at the chosen model
    ///

    /// details | What this notebook runs on your machine
        type: warning

    Each attempt clones the repository you choose into a temporary directory and lets the model read, search and
    edit files there. Shell commands requested by the model are limited to a read-only allowlist (`ls`, `cat`,
    `grep`, read-only `git`, ...) with no pipes or redirects. Model and judge requests are billed to the API keys you
    provide, and every prompt, diff and tool call is logged to the Weave project you choose.
    ///
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ---
    ## Connect

    /// admonition | Credentials
        type: info

    - **W&B API key** (`WANDB_API_KEY`): traces every run to your **Weave project** (`entity/project`), and also
      authenticates the open models on CoreWeave Serverless Inference (`https://api.inference.wandb.ai/v1`).
    - **Serverless Inference usage project** (`team/project`): sent as the `OpenAI-Project` header. **Required:**
      without it, Serverless Inference rejects a valid key with `401 invalid_api_key`.
    - **Anthropic API key** (`ANTHROPIC_API_KEY`): the closed-model baseline and the judge that grades every attempt.
    - **Serverless Inference API key** (`SI_API_KEY`, optional): only if you want SI billed to a different key.

    Keys already set in the environment are detected and do not need to be pasted. Keys are kept in this
    notebook process only.
    ///
    """)
    return


@app.cell(hide_code=True)
def _():
    _detected = {k: bool(os.environ.get(k)) for k in ("SI_API_KEY", "ANTHROPIC_API_KEY", "WANDB_API_KEY")}

    def _key_field(name: str) -> mo.ui.text:
        return mo.ui.text(
            kind="password", placeholder="(detected in environment)" if _detected[name] else "", full_width=True
        )

    creds_form = (
        mo.md("""
        - **Serverless Inference API key:** {si_key}
        - **Anthropic API key:** {anthropic_key}
        - **W&B API key:** {wandb_key}
        - **Weave project** (`entity/project`): {weave_project}
        - **Serverless Inference usage project** (`team/project`, required): {si_project}
        """)
        .batch(
            si_key=_key_field("SI_API_KEY"),  # type: ignore
            anthropic_key=_key_field("ANTHROPIC_API_KEY"),  # type: ignore
            wandb_key=_key_field("WANDB_API_KEY"),  # type: ignore
            weave_project=mo.ui.text(
                value=os.environ.get("WEAVE_PROJECT", ""), placeholder="my-team/coding-agent-eval", full_width=True
            ),  # type: ignore
            si_project=mo.ui.text(placeholder="my-team/coding-agent-eval", full_width=True),  # type: ignore
        )
        .form(submit_button_label="Save", clear_on_submit=False, bordered=False)
    )
    creds_form
    return (creds_form,)


@app.cell(hide_code=True)
def _(creds_form: mo.ui.form):
    _v = creds_form.value or {}
    for _field, _env in (
        ("si_key", "SI_API_KEY"),
        ("anthropic_key", "ANTHROPIC_API_KEY"),
        ("wandb_key", "WANDB_API_KEY"),
    ):
        if _v.get(_field):
            os.environ[_env] = _v[_field].strip()
    weave_project = (_v.get("weave_project") or os.environ.get("WEAVE_PROJECT") or "").strip()
    si_project = (_v.get("si_project") or "").strip() or None

    _status = {
        "Serverless Inference": bool(os.environ.get("SI_API_KEY") or os.environ.get("WANDB_API_KEY"))
        and bool(si_project),
        "Anthropic (baseline + judge)": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "W&B": bool(os.environ.get("WANDB_API_KEY")),
        "Weave project": "/" in weave_project,
    }
    _missing = [k for k, ok in _status.items() if not ok]
    mo.callout(
        mo.md(
            " · ".join(f"{'✅' if ok else '⬜'} {k}" for k, ok in _status.items())
            + ("" if not _missing else f"<br><br>Still needed before running the evaluation: **{', '.join(_missing)}**")
        ),
        kind="success" if not _missing else "warn",
    )
    return si_project, weave_project


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ---
    ## Build Your Task Set

    /// admonition | Tasks from merged PRs
        type: info

    Each task replays one merged pull request. The agent starts from the commit **just before** the merge, receives
    the PR title and description (plus the body of any issue it closes) as its instructions, and its attempt is graded
    against the diff that actually merged.

    Changes are filtered so the set reflects real coding-agent work: dependency bumps, CI-only and docs-only changes,
    lockfiles, generated code and changelogs are dropped, and very large PRs are skipped. The sample mixes
    **quick edits** (single file, small diff) and **features** (multi-file). Optionally, the largest features are also
    added as **planning** tasks, where the agent explores read-only and is graded on its implementation plan.

    Any repository `git clone` can reach works, including private repos your git credentials can read.
    About **30 tasks** is enough to separate models; start with 5–10 to check the setup.
    ///
    """)
    return


@app.cell(hide_code=True)
def _():
    task_form = (
        mo.md("""
        - **Repository** (URL or local path): {repo}
        - **Edit tasks:** {n_tasks}  ·  **Planning tasks:** {n_plan}
        - **Max changed lines per PR:** {max_lines}  ·  **Max files per PR:** {max_files}
        - **Recent commits to scan:** {scan_limit}
        """)
        .batch(
            repo=mo.ui.text(placeholder="https://github.com/your-org/your-repo", full_width=True),  # type: ignore
            n_tasks=mo.ui.number(start=1, stop=200, value=30),  # type: ignore
            n_plan=mo.ui.number(start=0, stop=50, value=5),  # type: ignore
            max_lines=mo.ui.number(start=10, stop=5000, value=400),  # type: ignore
            max_files=mo.ui.number(start=1, stop=100, value=10),  # type: ignore
            scan_limit=mo.ui.number(start=50, stop=5000, value=500),  # type: ignore
        )
        .form(submit_button_label="Build Tasks", clear_on_submit=False)
    )
    task_form
    return (task_form,)


@app.cell(hide_code=True)
def _(task_form: mo.ui.form):
    _v = task_form.value
    mo.stop(not _v or not (_v.get("repo") or "").strip(), mo.md("_Enter a repository above to build tasks._"))

    tasks: list[dict] = []
    with mo.status.spinner(title="Mining merged PRs (the first clone can take a minute)"):
        try:
            tasks = build_tasks(
                _v["repo"].strip(),
                n_tasks=int(_v["n_tasks"]),
                n_plan_tasks=int(_v["n_plan"]),
                max_lines=int(_v["max_lines"]),
                max_files=int(_v["max_files"]),
                scan_limit=int(_v["scan_limit"]),
            )
            _out = None
        except Exception as _e:
            _out = mo.callout(mo.md(f"Could not build tasks: `{_e}`"), kind="danger")

    if tasks:
        _df = pd.DataFrame(
            [
                {
                    "task": t["task_id"],
                    "category": t["category"],
                    "files": len(t["reference_files"]),
                    "lines": t["lines_added"] + t["lines_removed"],
                    "title": t["title"],
                }
                for t in tasks
            ]
        )
        _mix = _df["category"].value_counts().to_dict()
        _out = mo.vstack(
            [
                mo.callout(
                    mo.md(
                        f"Built **{len(tasks)} tasks**: "
                        + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in _mix.items())
                    ),
                    kind="success",
                ),
                mo.ui.table(_df, selection=None, page_size=10),
                mo.accordion({"Example task prompt": mo.md(f"```\n{tasks[0]['prompt'][:3000]}\n```")}),
            ]
        )
    _out
    return (tasks,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ---
    ## Choose Models

    /// admonition | Three or four open models, plus your current closed model
        type: info

    The defaults compare a purpose-built coding model, a large generalist, and a fast low-cost model — the class most
    worth checking for dropped tool calls — against a Claude baseline. Prices are USD per 1M tokens and are only used
    for cost accounting; edit them to match your contract.

    To test a model that is not on Serverless Inference — a Dedicated Inference gateway, vLLM on CKS (including spot
    capacity), or another OpenAI-compatible provider — add it as a custom endpoint.
    ///
    """)
    return


@app.cell(hide_code=True)
def _():
    model_picker = mo.ui.multiselect(
        options=list(PRESETS), value=DEFAULT_LINEUP, label="**Models to evaluate**", full_width=True
    )
    custom_form = (
        mo.md("""
        **Custom OpenAI-compatible endpoint** (optional)

        - **Label:** {label}  ·  **Model ID:** {model}
        - **Base URL:** {base_url}
        - **API key:** {api_key}
        - **Price per 1M input / output tokens:** {input_price} / {output_price}
        """)
        .batch(
            label=mo.ui.text(placeholder="my-vllm-endpoint"),  # type: ignore
            model=mo.ui.text(placeholder="org/model-name"),  # type: ignore
            base_url=mo.ui.text(placeholder="https://my-gateway.example.com/v1", full_width=True),  # type: ignore
            api_key=mo.ui.text(kind="password", full_width=True),  # type: ignore
            input_price=mo.ui.number(start=0, stop=100, step=0.01, value=0),  # type: ignore
            output_price=mo.ui.number(start=0, stop=100, step=0.01, value=0),  # type: ignore
        )
        .form(submit_button_label="Add Endpoint", clear_on_submit=False)
    )
    mo.vstack([model_picker, mo.accordion({"Add a custom endpoint": custom_form})])
    return custom_form, model_picker


@app.cell(hide_code=True)
def _(custom_form: mo.ui.form, model_picker: mo.ui.multiselect):
    _rows = []
    for _name in model_picker.value:
        _s = PRESETS[_name]
        _rows.append(
            {"label": _s.label, "model": _s.model, "provider": _s.provider,
             "input_price": _s.input_price, "output_price": _s.output_price}
        )  # fmt: skip
    _c = custom_form.value or {}
    custom_spec = None
    if _c.get("label") and _c.get("model") and _c.get("base_url"):
        _env = "CUSTOM_ENDPOINT_" + "".join(ch if ch.isalnum() else "_" for ch in _c["label"]).upper() + "_KEY"
        if _c.get("api_key"):
            os.environ[_env] = _c["api_key"]
        custom_spec = ModelSpec(
            label=_c["label"].strip(), model=_c["model"].strip(), base_url=_c["base_url"].strip(), api_key_env=_env,
            input_price=float(_c["input_price"]) or None, output_price=float(_c["output_price"]) or None,
        )  # fmt: skip
        _rows.append(
            {"label": custom_spec.label, "model": custom_spec.model, "provider": "openai (custom)",
             "input_price": custom_spec.input_price, "output_price": custom_spec.output_price}
        )  # fmt: skip

    price_editor = mo.ui.data_editor(pd.DataFrame(_rows), label="Edit prices if needed (USD per 1M tokens)")
    price_editor
    return custom_spec, price_editor


@app.cell(hide_code=True)
def _(custom_spec: ModelSpec | None, model_picker: mo.ui.multiselect, price_editor, si_project: str | None):
    _prices = {r["label"]: r for r in pd.DataFrame(price_editor.value).to_dict("records")}

    def _apply(spec: ModelSpec) -> ModelSpec:
        p = _prices.get(spec.label, {})
        overrides = {"input_price": p.get("input_price"), "output_price": p.get("output_price")}
        if spec.provider == "openai" and spec.base_url == SI_BASE_URL:
            overrides["project"] = si_project
        return spec.with_overrides(**{k: v for k, v in overrides.items() if k == "project" or v is not None})

    specs = [_apply(PRESETS[n]) for n in model_picker.value] + ([_apply(custom_spec)] if custom_spec else [])
    _missing_keys = sorted({s.api_key_env for s in specs if not s.api_key()})
    mo.callout(
        mo.md(
            f"**{len(specs)} models selected.**"
            + (f" Missing keys: `{', '.join(_missing_keys)}` — add them under **Connect**." if _missing_keys else "")
        ),
        kind="warn" if _missing_keys else "info",
    )
    return (specs,)


@app.cell(hide_code=True)
def _():
    mo.md(rf"""
    ---
    ## Probe Tool Calls

    /// admonition | Does each model's tool call survive your serving stack?
        type: info

    A coding agent only works if its tool calls arrive as tool calls. When the serving stack's parser does not
    recognize a model's tool-call format, the call either **leaks** into the reply as text or is **dropped**
    entirely — and because the agent receives a normal-looking response, nothing errors. It just stops reading files
    and making edits. We have seen a widely recommended fast model do exactly this for a customer until a parser fix
    shipped.

    This probe sends {len(PROBES)} single-turn requests per model where the only correct response is a specific tool
    call: arguments full of quotes, backslashes and non-ASCII text; a long file write; a call deep into a trajectory;
    and the final `finish` call. Each runs with streaming on and off, because servers parse those two paths with
    different code. It takes about a minute and costs cents.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(specs: list):
    probe_button = mo.ui.run_button(label="Run tool-call probe")
    probe_trials = mo.ui.slider(start=1, stop=10, value=3, label="Trials per probe")
    mo.hstack([probe_trials, probe_button], justify="start")
    return probe_button, probe_trials


@app.cell(hide_code=True)
def _(probe_button: mo.ui.run_button, probe_trials: mo.ui.slider, specs: list):
    mo.stop(not probe_button.value, mo.md("_Click **Run tool-call probe** to start._"))
    with mo.status.spinner(title="Probing tool calls"):
        _rows = run_probe(specs, trials=int(probe_trials.value))
    _summary = pd.DataFrame(summarize_probe(_rows))
    _summary["mode"] = _summary["stream"].map({True: "streaming", False: "non-streaming"})
    _chart = (
        alt.Chart(_summary)
        .mark_bar()
        .encode(
            x=alt.X(
                "tool_call_survival:Q",
                title="Tool calls that arrived as tool calls",
                scale=alt.Scale(domain=[0, 1]),
                axis=alt.Axis(format="%"),
            ),
            y=alt.Y("model:N", title=None, sort="-x"),
            yOffset="mode:N",
            color=alt.Color("mode:N", title=None),
            tooltip=["model", "mode", "tool_call_survival", "dropped", "leaked", "malformed_args", "truncated"],
        )
        .properties(height=alt.Step(14))
    )
    _failures = pd.DataFrame([r for r in _rows if r["result"] not in ("ok",)])
    mo.vstack(
        [
            mo.ui.altair_chart(_chart),
            mo.ui.table(_summary.drop(columns=["stream"]), selection=None),
            mo.accordion(
                {
                    "Every non-ok probe response": mo.ui.table(_failures, selection=None)
                    if len(_failures)
                    else mo.md("None — every probe passed.")
                }
            ),
            mo.md(
                "_`tool_call_survival` counts format failures only (dropped, leaked, malformed, truncated). "
                "`wrong_tool` and `bad_content` are reasoning misses, not serving problems._"
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ---
    ## Run the Evaluation

    /// admonition | How each attempt runs
        type: info

    Every attempt gets a fresh checkout of the task's starting commit and runs a small, instrumented agent loop with
    six tools (list, read, search, edit, write, and a read-only `run_command`). Every model call and tool call is
    traced in Weave. A frontier model then grades the resulting diff (or plan) against the merged change.

    **Harness profile** controls how much the harness forgives:

    - **strict** — malformed calls get an error back; a leaked or dropped call ends the attempt. This measures the
      model and serving stack as they are.
    - **forgiving** — repairs malformed JSON, recovers tool calls written as text, and nudges the model to continue
      after a silent stop, like a mature coding harness would.

    Run both to see how much a harness is hiding. Runs are not free: check the estimate before you start.
    ///
    """)
    return


@app.cell(hide_code=True)
def _():
    run_form = (
        mo.md("""
        - **Trials per task:** {trials}  ·  **Harness profiles:** {profiles}
        - **Parallel attempts:** {parallelism}  ·  **Max turns per attempt:** {max_turns}
        - **Judge model:** {judge_model}  ·  **Limit tasks** (0 = all): {limit}
        """)
        .batch(
            trials=mo.ui.number(start=1, stop=10, value=3),  # type: ignore
            profiles=mo.ui.multiselect(options=["strict", "forgiving"], value=["strict"]),  # type: ignore
            parallelism=mo.ui.number(start=1, stop=64, value=8),  # type: ignore
            max_turns=mo.ui.number(start=5, stop=200, value=50),  # type: ignore
            judge_model=mo.ui.dropdown(options=list(JUDGES), value=next(iter(JUDGES))),  # type: ignore
            limit=mo.ui.number(start=0, stop=500, value=0),  # type: ignore
        )
        .form(submit_button_label="Confirm settings", clear_on_submit=False)
    )
    run_form
    return (run_form,)


@app.cell(hide_code=True)
def _(run_form: mo.ui.form, specs: list, tasks: list):
    _v = run_form.value
    mo.stop(not _v, mo.md("_Confirm the run settings above._"))
    mo.stop(not tasks, mo.md("_Build a task set above first._"))
    run_tasks = tasks[: int(_v["limit"])] if int(_v["limit"]) else tasks
    _profiles = _v["profiles"] or ["strict"]
    _est = estimate_requests(len(run_tasks), len(specs), int(_v["trials"]))
    _attempts = int(_est["attempts"]) * len(_profiles)
    run_button = mo.ui.run_button(label=f"Run {_attempts} attempts", kind="danger")
    mo.vstack(
        [
            mo.callout(
                mo.md(
                    f"**{len(run_tasks)} tasks × {len(specs)} models × {_v['trials']} trials × {len(_profiles)} profile(s) "
                    f"= {_attempts} attempts**, roughly {int(_est['model_requests']) * len(_profiles):,} model requests and "
                    f"{_attempts} judge calls. Start with a small task limit to check the setup before a full run."
                ),
                kind="warn",
            ),
            run_button,
        ]
    )
    return run_button, run_tasks


@app.cell(hide_code=True)
def _(
    run_button: mo.ui.run_button,
    run_form: mo.ui.form,
    run_tasks: list,
    specs: list,
    si_project: str | None,
    weave_project: str,
):
    mo.stop(not run_button.value, mo.md("_Click the run button to start the evaluation._"))
    mo.stop(
        "/" not in weave_project,
        mo.callout(mo.md("Set a Weave project (`entity/project`) under **Connect**."), kind="danger"),
    )

    _v = run_form.value
    _judge = JUDGES[_v["judge_model"]](si_project)  # one judge object shared by every evaluation
    run_results = []
    suite_name = f"coding-agent-eval-{pd.Timestamp.now(tz='UTC').strftime('%Y%m%d-%H%M%S')}"
    for _profile in _v["profiles"] or ["strict"]:
        mo.output.append(mo.md(f"Running **{_profile}** profile…"))
        _res = run_suite(
            run_tasks,
            specs,
            project=weave_project,
            suite_name=suite_name,
            trials=int(_v["trials"]),
            profile=_profile,
            judge=_judge,
            parallelism=int(_v["parallelism"]),
            max_turns=int(_v["max_turns"]),
            on_model_done=lambda label, _s, p=_profile: mo.output.append(mo.md(f"✅ `{label}` · {p} done")),
        )
        run_results.append({"profile": _profile, **_res})
    mo.output.append(mo.callout(mo.md("Evaluation complete — see **Results** below."), kind="success"))
    return run_results, suite_name


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ---
    ## Results

    - **completion_rate** — share of attempts the judge would accept as completing the task.
    - **tool_call_accuracy** — share of tool-call attempts that arrived well-formed, *before* any harness repair.
    - **silent_stop_rate** — attempts that ended because a tool call leaked or was dropped.
    - **cost_per_success** — total spend on all attempts divided by the attempts that passed. This is the number to
      compare: a cheap model that needs three tries is not cheap.
    """)
    return


@app.cell(hide_code=True)
def _(run_results: list, suite_name: str):
    attempt_rows = pd.DataFrame(collect_rows(suite_name))
    board = pd.DataFrame(leaderboard(attempt_rows.to_dict("records")))
    _links = []
    for _r in run_results:
        if _r.get("compare_url"):
            _links.append(f"[Compare in Weave ({_r['profile']})]({_r['compare_url']})")
    _links.append(f"[All evaluations]({run_results[0]['project_url']})")

    _scatter = (
        alt.Chart(board.dropna(subset=["cost_per_success"]))
        .mark_circle(size=160)
        .encode(
            x=alt.X("cost_per_success:Q", title="Cost per successful task (USD)", scale=alt.Scale(type="log")),
            y=alt.Y(
                "completion_rate:Q", title="Completion rate", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])
            ),
            color=alt.Color("model:N"),
            shape=alt.Shape("profile:N"),
            tooltip=list(board.columns),
        )
        .properties(height=320, title="Up and to the left is better")
    )
    mo.vstack([mo.md(" · ".join(_links)), mo.ui.table(board, selection=None), mo.ui.altair_chart(_scatter)])
    return attempt_rows, board


@app.cell(hide_code=True)
def _(attempt_rows: pd.DataFrame):
    _by_cat = (
        attempt_rows.dropna(subset=["passed"])
        .assign(passed=lambda d: d["passed"].astype(float))
        .groupby(["model", "profile", "category"], as_index=False)["passed"]
        .mean()
    )
    _cat_chart = (
        alt.Chart(_by_cat)
        .mark_bar()
        .encode(
            x=alt.X("passed:Q", title="Completion rate", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("model:N", title=None),
            yOffset="profile:N",
            color="profile:N",
            column=alt.Column("category:N", title=None),
            tooltip=["model", "profile", "category", alt.Tooltip("passed:Q", format=".0%")],
        )
        .properties(width=180)
    )
    _failures = attempt_rows.groupby(["model", "profile"], as_index=False)[
        ["n_dropped", "n_leaked", "n_malformed_args", "n_truncated", "repairs", "nudges"]
    ].sum()
    mo.vstack(
        [
            mo.md("### By task type\nA model can be the right pick for quick edits and the wrong one for planning."),
            mo.ui.altair_chart(_cat_chart),
            mo.md(
                "### Tool-call failures\nCounts across all attempts. `repairs` and `nudges` are the forgiving harness covering for them."
            ),
            mo.ui.table(_failures, selection=None),
        ]
    )
    return


@app.cell(hide_code=True)
def _(board: pd.DataFrame):
    mo.stop(board["profile"].nunique() < 2, mo.md("_Run both harness profiles to see how much the harness hides._"))
    _pivot = board.pivot_table(index="model", columns="profile", values="completion_rate").reset_index()
    _pivot["hidden_by_harness"] = _pivot["forgiving"] - _pivot["strict"]
    mo.vstack(
        [
            mo.md(
                "### What the harness is hiding\n"
                "The gap between profiles is failure your developers would not see in a forgiving harness — "
                "but would pay for in retries, latency and tokens."
            ),
            mo.ui.table(_pivot.sort_values("hidden_by_harness", ascending=False), selection=None),
        ]
    )
    return


@app.cell(hide_code=True)
def _(attempt_rows: pd.DataFrame, board: pd.DataFrame):
    _rows = []
    for _profile in sorted(attempt_rows["profile"].dropna().unique()):
        _lad = escalation_ladder(attempt_rows[attempt_rows["profile"] == _profile].to_dict("records"))
        _best = board[board["profile"] == _profile].dropna(subset=["cost_per_success"])
        _best = _best.sort_values("cost_per_success").iloc[0] if len(_best) else None
        _rows.append(
            {
                "profile": _profile,
                "ladder (cheapest first)": " → ".join(_lad["order"]),
                "ladder completion": _lad["expected_completion_rate"],
                "ladder cost_per_success": _lad["cost_per_success"],
                "best single model": None if _best is None else _best["model"],
                "its completion": None if _best is None else _best["completion_rate"],
                "its cost_per_success": None if _best is None else _best["cost_per_success"],
            }
        )
    mo.vstack(
        [
            mo.md(
                "### Would routing pay off?\n"
                "A router sends each task to a cheap model and escalates when it fails. This simulates that from "
                "your results: try models cheapest-first, stop at the first pass. It assumes failures are "
                "detectable (tests, review, or a judge), which is the best case for routing. If the best single "
                "model is close, a router adds moving parts for little gain."
            ),
            mo.ui.table(pd.DataFrame(_rows), selection=None),
        ]
    )
    return


@app.cell(hide_code=True)
def _(attempt_rows: pd.DataFrame):
    failure_model = mo.ui.dropdown(
        options=sorted(attempt_rows["model"].dropna().unique()), label="Inspect failed attempts for"
    )
    failure_model
    return (failure_model,)


@app.cell(hide_code=True)
def _(attempt_rows: pd.DataFrame, failure_model: mo.ui.dropdown):
    mo.stop(not failure_model.value)
    _failed = attempt_rows[(attempt_rows["model"] == failure_model.value) & (attempt_rows["passed"] != True)]  # noqa: E712
    mo.ui.table(
        _failed[
            ["profile", "task_id", "category", "verdict", "stop_reason", "turns", "diff_lines", "rationale", "error"]
        ],
        selection=None,
        page_size=10,
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ---
    ## Use the Winner

    /// admonition | Bring the model to the harness your developers already use
        type: info

    Serverless Inference speaks the OpenAI Chat Completions API, so any coding tool with an OpenAI-compatible provider
    can use it. After you pick a model, re-run the **Probe Tool Calls** section through that tool's own setup if you
    can: the harness is part of the stack, and its tool-call handling matters as much as the model's.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(specs: list):
    _open = [s for s in specs if s.provider == "openai"]
    winner_pick = mo.ui.dropdown(
        options=[s.model for s in _open], value=_open[0].model if _open else None, label="Model to configure"
    )
    winner_pick
    return (winner_pick,)


@app.cell(hide_code=True)
def _(winner_pick: mo.ui.dropdown):
    mo.stop(not winner_pick.value)
    _m = winner_pick.value
    mo.ui.tabs(
        {
            "Cline": mo.md(f"""
Documented in the [Serverless Inference Cline tutorial](https://docs.coreweave.com/products/inference/serverless/tutorials/integration-cline):

```bash
cline auth -k "$SI_API_KEY" -p openai -b {SI_BASE_URL} -m {_m}
```
"""),
            "OpenCode": mo.md(f"""
`opencode.json` in your project root (not yet verified end to end with this kit):

```json
{{
  "$schema": "https://opencode.ai/config.json",
  "provider": {{
    "coreweave": {{
      "npm": "@ai-sdk/openai-compatible",
      "name": "CoreWeave Serverless Inference",
      "options": {{ "baseURL": "{SI_BASE_URL}", "apiKey": "{{env:SI_API_KEY}}" }},
      "models": {{ "{_m}": {{ "name": "{_m}" }} }}
    }}
  }},
  "model": "coreweave/{_m}"
}}
```
"""),
            "Any OpenAI-compatible tool": mo.md(f"""
```bash
export OPENAI_BASE_URL={SI_BASE_URL}
export OPENAI_API_KEY="$SI_API_KEY"
# model name: {_m}
```
"""),
        }
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ---
    ## Going Further

    - **Run tests, not just review diffs.** `run_command` is read-only here. Run attempts in a
      [CoreWeave Sandbox](https://docs.coreweave.com/products/sandboxes) to let agents execute your test suite safely,
      and add a test-pass scorer alongside the judge.
    - **Check the judge.** Spot-check a sample of verdicts against your own reviewers' judgement before relying on
      close results, and avoid using the same model as both a candidate and the judge when the margin is narrow.
    """)
    return


if __name__ == "__main__":
    app.run()
