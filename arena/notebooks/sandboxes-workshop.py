# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "cwsandbox>=0.23.2",
#     "httpx>=0.28.1",
#     "marimo>=0.23.6",
#     "weave>=0.52.0",
# ]
# ///

import marimo

__generated_with = "0.20.2"
app = marimo.App(width="medium", app_title="CoreWeave ARENA")

with app.setup:
    import json
    import os
    import signal

    import httpx
    import marimo as mo
    import weave
    from lib.coreweave import cw_token_input, detect_cw_token
    from lib.ui import about, banner, security_disclaimer, table_of_contents

    _orig_signal = signal.signal

    def _safe_signal(sig, handler):
        try:
            return _orig_signal(sig, handler)
        except ValueError:
            return None

    signal.signal = _safe_signal
    from cwsandbox import AuthHeaders, Sandbox, set_auth_mode
    signal.signal = _orig_signal


# ----------------------------------------------------------------- #
# Header                                                            #
# ----------------------------------------------------------------- #
@app.cell(hide_code=True)
def _():
    _elements = [
        banner(),
        about(
            "Sandboxes Workshop",
            """Walk through the full lifecycle of a CoreWeave <b>Sandbox</b>:
            author a profile, deploy a runner on a CKS cluster, launch
            sandboxes from the Python SDK, and run a parallel
            reward-evaluation batch — the inner loop of RL with verifiable
            rewards.
            """,
        ),
        table_of_contents(
            [
                {"title": "Connect", "description": "Paste your CoreWeave API access token"},
                {"title": "Step 1 — Author a profile", "description": "Choose namespace + egress + runtime class"},
                {"title": "Step 2 — Deploy a runner", "description": "Submit + poll until ready"},
                {"title": "Step 3 — First sandbox", "description": "Python SDK round-trip"},
                {"title": "Step 4 — RL with verifiable rewards", "description": "Parallel sandboxes, rewards arrive as they finish"},
                {"title": "Step 5 — Observability with Weave", "description": "Trace every reward call to W&B"},
                {"title": "Step 6 — Cleanup", "description": "Tear it all down"},
            ]
        ),
        security_disclaimer(),
    ]
    mo.vstack(_elements)
    return


# ----------------------------------------------------------------- #
# Prerequisites                                                      #
# ----------------------------------------------------------------- #
@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Prerequisites

    Before you begin, make sure you have:

    - **A CKS cluster** in your CoreWeave org. 
    - **IAM action `SANDBOX_ADMIN`** on your access policy — grants create/update on profiles and runners (transitively grants `SANDBOX_USER` for launching sandboxes). Add it at [console.coreweave.com → Access Policies](https://console.coreweave.com/security-and-access/access-policies).
    - **A CoreWeave API access token** *(required)* — generate at [console.coreweave.com → Tokens](https://console.coreweave.com/security-and-access/tokens) and copy the Token Secret. The notebook will try to discover a token automatically (Arena pod identity, the `CW_TOKEN` env var, or a kubeconfig that carries one) and only fall back to the Connect form below if nothing is found. Same token is used for both the REST control plane and the Python SDK.
    - **A W&B API key** *(optional)* — only needed to see Weave traces in Step 4. Get one at [wandb.ai/authorize](https://wandb.ai/authorize). Skip if you don't need run-level observability.
    """)
    return


# ----------------------------------------------------------------- #
# Connect: auto-detect CW token; fall back to a form                #
# ----------------------------------------------------------------- #
@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Connect
    """)
    return


@app.cell(hide_code=True)
def _():
    auto_token, auto_source = detect_cw_token()
    return auto_source, auto_token


@app.cell(hide_code=True)
def _(auto_source: str, auto_token: str):
    _wandb_widget = mo.ui.text(
        label="W&B API key (optional, for Weave tracing)",
        kind="password",
        placeholder="(optional)",
        full_width=True,
    )
    if auto_token:
        _intro = mo.callout(
            mo.md(
                f"✅ **CoreWeave token auto-detected** via `{auto_source}`. "
                "The notebook is already authenticated. Optionally add a W&B "
                "key for Weave tracing on Step 4, then press Continue."
            ),
            kind="success",
        )
        cw_token_form = (
            mo.md("{wandb_token}")
            .batch(wandb_token=_wandb_widget)
            .form(submit_button_label="Continue", bordered=False)
        )
        _rendered = mo.vstack([_intro, cw_token_form])
    else:
        _rendered, cw_token_form = cw_token_input(
            extra_fields={"wandb_token": _wandb_widget}
        )
    _rendered
    return (cw_token_form,)


@app.cell(hide_code=True)
def _(auto_token: str, cw_token_form: mo.ui.form):
    _v = cw_token_form.value or {}
    if auto_token:
        cw_token = auto_token
        wandb_token = _v.get("wandb_token") or None
    else:
        # No auto-detected token — the form is the only source.
        cw_token = _v.get("cw_token")
        wandb_token = _v.get("wandb_token") or None
        mo.stop(not cw_token, mo.md("_Submit the Connect form above to continue._"))

    # Register the CoreWeave token with the cwsandbox SDK through its
    # documented auth hook. The token lives only in this lambda's closure
    # — it never enters the process environment, so it isn't visible to
    # child processes or persisted to shell history.
    set_auth_mode(
        "sandboxes-workshop",
        lambda: AuthHeaders(
            headers={"Authorization": f"Bearer {cw_token}"},
            strategy="api_key",
        ),
    )

    # Weave (W&B) reads WANDB_API_KEY from the environment at wandb.init()
    # and has no equivalent callback hook, so this one has to be env-scoped.
    if wandb_token:
        os.environ["WANDB_API_KEY"] = wandb_token

    SANDBOX_API = "https://api.coreweave.com/v1beta2/sandbox"
    _headers = {"Authorization": f"Bearer {cw_token}", "Content-Type": "application/json"}

    def sandbox_get(path: str) -> httpx.Response:
        return httpx.get(f"{SANDBOX_API}{path}", headers=_headers, timeout=30.0)

    def sandbox_post(path: str, body: dict) -> httpx.Response:
        return httpx.post(f"{SANDBOX_API}{path}", headers=_headers, json=body, timeout=60.0)

    def sandbox_delete(path: str) -> httpx.Response:
        return httpx.delete(f"{SANDBOX_API}{path}", headers=_headers, timeout=30.0)

    _probe = sandbox_get("/profile-templates")
    _connect_msgs = []
    if _probe.status_code != 200:
        _connect_msgs.append(f"❌ **Sandbox API unreachable** — HTTP {_probe.status_code}\n\n```\n{_probe.text[:500]}\n```")
        _kind = "danger"
    else:
        _connect_msgs.append(
            f"✅ **Sandbox API connected.** "
            f"{len(_probe.json().get('profileTemplates', []))} existing profiles in your org."
        )
        _kind = "success"

    weave_url: str | None = None
    if wandb_token:
        try:
            _weave_client = weave.init("sandboxes-workshop")
            _entity = getattr(_weave_client, "entity", None)
            _project = getattr(_weave_client, "project", "sandboxes-workshop")
            if _entity:
                weave_url = f"https://wandb.ai/{_entity}/{_project}/weave"
                _connect_msgs.append(f"✅ **Weave tracing enabled** — [view dashboard]({weave_url})")
            else:
                _connect_msgs.append("✅ **Weave tracing enabled** (Step 4 will log to your wandb account).")
        except Exception as _exc:
            _connect_msgs.append(f"⚠️ **Weave init failed:** `{type(_exc).__name__}: {_exc}` (Step 4 will run without tracing.)")
    else:
        _connect_msgs.append("ℹ️ W&B token not provided — Step 4 will run without Weave tracing.")

    _connect_status = mo.callout(mo.md("\n\n".join(_connect_msgs)), kind=_kind)
    _connect_status
    return cw_token, sandbox_delete, sandbox_get, sandbox_post, wandb_token, weave_url


# ----------------------------------------------------------------- #
# Cluster identity (used as input for runner deploy)                #
# ----------------------------------------------------------------- #
@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Cluster identity

    The runner is deployed onto a specific CKS cluster. Pick from the clusters
    your token can access — this list is fetched live from the CoreWeave
    Platform API.
    """)
    return


@app.cell(hide_code=True)
def _(cw_token: str | None):
    mo.stop(not cw_token, mo.md("_Connect first to populate the cluster list._"))

    _resp = httpx.get(
        "https://api.coreweave.com/v1beta1/cks/clusters",
        headers={"Authorization": f"Bearer {cw_token}"},
        timeout=15.0,
    )
    if _resp.status_code != 200:
        cluster_form = None
        _rendered = mo.callout(
            mo.md(
                f"❌ **Couldn't list clusters** — HTTP {_resp.status_code}\n\n"
                f"```\n{_resp.text[:400]}\n```"
            ),
            kind="danger",
        )
    else:
        _running = [
            c for c in _resp.json().get("items", [])
            if c.get("status") == "STATUS_RUNNING"
        ]
        _running.sort(key=lambda c: (c.get("zone", ""), c.get("name", "")))

        if not _running:
            cluster_form = None
            _rendered = mo.callout(
                mo.md("❌ **No running clusters found in your org.** Provision a CKS cluster first."),
                kind="danger",
            )
        else:
            # Dropdown options: human label → (zone, name) tuple
            _options = {
                f"{c['zone'].lower()} / {c['name']}": (c["zone"].lower(), c["name"])
                for c in _running
            }
            cluster_form = (
                mo.md("""
                - CKS cluster: {cluster}
                - Runner ID: {runner_id}
                """)
                .batch(
                    cluster=mo.ui.dropdown(options=_options),
                    runner_id=mo.ui.text(value="workshop-runner"),
                )
                .form(submit_button_label="Use these values", bordered=False)
            )
            _rendered = cluster_form
    _rendered
    return (cluster_form,)


@app.cell(hide_code=True)
def _(cluster_form):
    mo.stop(cluster_form is None, mo.md("_(no cluster list available — see error above)_"))

    _v = cluster_form.value or {}
    mo.stop(
        not _v.get("cluster"),
        mo.md("_Pick a cluster from the dropdown and press **Use these values**._"),
    )

    cluster_zone, cluster_name = _v["cluster"]
    runner_id = _v.get("runner_id") or "workshop-runner"

    _status = mo.callout(
        mo.md(
            "✅ **Using these values:**\n\n"
            f"- Cluster zone: `{cluster_zone}`\n"
            f"- Cluster name: `{cluster_name}`\n"
            f"- Runner ID: `{runner_id}`"
        ),
        kind="success",
    )
    _status
    return cluster_name, cluster_zone, runner_id


# ----------------------------------------------------------------- #
# Step 1 — Author a profile                                         #
# ----------------------------------------------------------------- #
@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Step 1 — Author a profile

    A **profile** defines the execution environment a sandbox can request:
    container image, runtime class, namespace strategy, network policy, and
    pod placement.

    Field reference (full schema in the [Profile reference docs](https://docs.coreweave.com/products/sandboxes/reference/profile)):

    - **Profile display name** — Human-readable name for the profile; unique within the org. Step 1 will 409 if you reuse a name — that's handled (we reuse the existing profile).
    - **Namespace strategy** — How sandboxes are grouped into Kubernetes namespaces. `per-user` isolates per researcher (typical for multi-tenant agent workloads); `per-org`, `per-profile`, and `static` are alternatives for shared-service or single-namespace setups. See [namespace strategies]('https://docs.coreweave.com/products/sandboxes/profiles/configure#choose-a-namespace-strategy').
    - **Egress mode** — Network policy applied to sandbox pods. `none` blocks all outbound traffic (safe default for untrusted code); `internet` allows public egress; `allowlist` permits only specific CIDRs. See [network policy](https://docs.coreweave.com/products/sandboxes/profiles/configure#network-policy).
    - **Runtime class** — Container runtime / isolation level. `(default)` uses containerd's `runc` (standard Linux containers, shared kernel — fine for trusted code). `gvisor` adds syscall-level isolation (recommended for untrusted code, requires gVisor-labeled nodes). `nvidia` is required for GPU sandboxes. See [runtime classes](https://docs.coreweave.com/products/sandboxes/profiles/configure#runtime-class).
    - **CPU / Memory limit** — Per-sandbox resource ceiling. Sandboxes can't exceed these even if the node has spare capacity. Lower = more sandboxes fit on a node; higher = each sandbox can do more work.

    Adjust the form, then press **Create profile**. Re-submitting with the same
    name reuses the existing profile (no duplicates). The cleanup step at the
    bottom only deletes the most recent profile ID.
    """)
    return


@app.cell(hide_code=True)
def _():
    profile_form = (
        mo.md("""
        - Profile display name: {name}
        - Namespace strategy: {namespace_strategy}
        - Egress mode: {egress_mode}
        - Runtime class: {runtime_class}
        - CPU limit: {cpu_limit}
        - Memory limit: {mem_limit}
        """)
        .batch(
            name=mo.ui.text(value="workshop-default"),
            namespace_strategy=mo.ui.dropdown(
                options=["per-user", "per-org", "per-profile", "static"], value="per-user"
            ),
            egress_mode=mo.ui.dropdown(options=["none", "internet", "allowlist"], value="none"),
            runtime_class=mo.ui.dropdown(options=["(default)", "gvisor", "nvidia"], value="(default)"),
            cpu_limit=mo.ui.text(value="500m"),
            mem_limit=mo.ui.text(value="512Mi"),
        )
        .form(submit_button_label="Create profile", bordered=False)
    )
    profile_form
    return (profile_form,)


@app.cell(hide_code=True)
def _(profile_form: mo.ui.form):
    """Render the resolved spec so attendees can see what will be POSTed.."""
    if not profile_form.value:
        _v = {
            "name": "workshop-default", "namespace_strategy": "per-user",
            "egress_mode": "none", "runtime_class": "(default)",
            "cpu_limit": "500m", "mem_limit": "512Mi",
        }
        _committed = False
    else:
        _v = profile_form.value
        _committed = True

    _egress_modes = {
        "none": {"deny-all": {"type": "none"}},
        "internet": {"internet": {"type": "internet"}},
        "allowlist": {"allowlist": {"type": "allowlist", "cidrs": ["140.82.112.0/20", "151.101.0.0/16"]}},
    }
    _egress_default = {"none": "deny-all", "internet": "internet", "allowlist": "allowlist"}[_v["egress_mode"]]

    profile_spec_body = {
        "displayName": _v["name"],
        "description": f"Workshop profile ({_v['namespace_strategy']} / {_v['egress_mode']})",
        "spec": {
            "resourceDefaults": {
                "cpuRequest": "250m", "memoryRequest": "256Mi",
                "cpuLimit": _v["cpu_limit"], "memoryLimit": _v["mem_limit"],
            },
            "namespaceConfigJson": json.dumps({"strategy": _v["namespace_strategy"]}),
            "networkConfigJson": json.dumps(
                {"egress": {"default": _egress_default, "modes": _egress_modes[_v["egress_mode"]]}}
            ),
        },
    }
    if _v["runtime_class"] != "(default)":
        profile_spec_body["spec"]["runtimeClass"] = _v["runtime_class"]

    mo.md(
        f"**Resolved spec to POST:**\n\n```json\n{json.dumps(profile_spec_body, indent=2)}\n```\n\n"
        f"_{'Submitted — see result below.' if _committed else 'Press the button to create.'}_"
    )
    return profile_spec_body, _committed


@app.cell(hide_code=True)
def _(cw_token: str | None, profile_form: mo.ui.form, profile_spec_body: dict, sandbox_get, sandbox_post):
    """Submit when the form has a fresh value. Idempotent: if a profile with
    this display_name already exists (HTTP 409), look it up by name and
    reuse its UUID instead of failing."""
    mo.stop(not cw_token or not profile_form.value)

    _resp = sandbox_post("/profile-templates", {"profileTemplate": profile_spec_body})

    if _resp.status_code == 409:
        # Name collision — find the existing profile and reuse its ID.
        _list = sandbox_get("/profile-templates")
        _matches = [
            p for p in (_list.json().get("profileTemplates", []) or [])
            if p.get("displayName") == profile_spec_body["displayName"]
        ]
        if _matches:
            profile_id = _matches[0].get("id")
            _out = mo.callout(
                mo.md(
                    f"♻️ **Profile `{profile_spec_body['displayName']}` already exists — reusing** `{profile_id}`.\n\n"
                    "To apply the new spec from the form above, use the *Update profile* "
                    "step inside Step 5 (PATCH). Step 1's create-only path won't overwrite "
                    "an existing profile by design."
                ),
                kind="info",
            )
        else:
            profile_id = None
            _out = mo.callout(
                mo.md(f"❌ 409 but no matching profile found in list — investigate:\n\n```\n{_resp.text[:500]}\n```"),
                kind="danger",
            )
    elif _resp.status_code >= 300:
        profile_id = None
        _out = mo.callout(
            mo.md(f"❌ **Profile create failed** — HTTP {_resp.status_code}\n\n```\n{_resp.text[:500]}\n```"),
            kind="danger",
        )
    else:
        _body = _resp.json()
        profile_id = _body.get("id") or _body.get("profileTemplate", {}).get("id")
        _out = mo.callout(
            mo.md(f"✅ **Created profile** `{profile_id}`"),
            kind="success",
        )
    _out
    return (profile_id,)


# ----------------------------------------------------------------- #
# Step 2 — Deploy a runner                                          #
# ----------------------------------------------------------------- #
@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Step 2 — Deploy a runner

    A **runner** is the CW-managed component inside a CKS cluster that places
    sandbox pods. The runner places, supervises, and tears down sandbox pods on that cluster.
    """)
    return


@app.cell(hide_code=True)
def _():
    deploy_runner_btn = mo.ui.run_button(label="Deploy runner", kind="success")
    deploy_runner_btn
    return (deploy_runner_btn,)


@app.cell(hide_code=True)
def _(
    cluster_name: str,
    cluster_zone: str,
    cw_token: str | None,
    deploy_runner_btn: mo.ui.run_button,
    profile_id: str | None,
    runner_id: str,
    sandbox_post,
):
    mo.stop(not cw_token, mo.md("_Connect first._"))
    mo.stop(not profile_id, mo.md("_Run Step 1 first._"))
    mo.stop(not deploy_runner_btn.value, mo.md("_Press 'Deploy runner' to submit._"))

    _body = {
        "runnerId": runner_id,
        "runner": {
            "identity": {"zone": cluster_zone, "clusterName": cluster_name},
            "managedSpec": {"releaseChannel": "RELEASE_CHANNEL_STABLE"},
            "profileBindings": [
                {"profileTemplateId": profile_id, "profileName": "default", "isDefault": True}
            ],
        },
    }
    _resp = sandbox_post("/managed-runners", _body)

    if _resp.status_code == 409:
        runner_submitted = True
        _out = mo.callout(
            mo.md(
                f"♻️ **Runner already exists on `{cluster_name}` — reusing it.**\n\n"
                f"Sandboxes will launch against the existing runner's profile binding "
                f"(not necessarily the profile you just created in Step 1). To start "
                f"fresh, delete it via Step 7, then re-run this cell."
            ),
            kind="info",
        )
    elif _resp.status_code >= 300:
        runner_submitted = False
        _out = mo.callout(
            mo.md(f"❌ **Runner deploy failed** — HTTP {_resp.status_code}\n\n```\n{_resp.text[:500]}\n```"),
            kind="danger",
        )
    else:
        runner_submitted = True
        _out = mo.callout(
            mo.md(f"✅ **Runner submitted** as `{runner_id}`. Polling state below — typical 20–60s."),
            kind="success",
        )
    _out
    return (runner_submitted,)


@app.cell(hide_code=True)
def _(
    cw_token: str | None,
    runner_id: str,
    runner_submitted: bool,
    sandbox_get,
):
    # Auto-poll until the runner reports READY + CONNECTED, or we hit
    # the timeout. Progress lines stream into the cell output as each
    # poll lands so the user can watch state evolve.
    mo.stop(
        not cw_token or not runner_submitted,
        mo.md("_Deploy a runner above to start polling._"),
    )

    import time as _time

    _poll_interval = 3.0
    _max_wait_s = 180.0
    _t0 = _time.time()

    mo.output.append(
        mo.md(f"⏳ Polling `{runner_id}` until READY + CONNECTED…")
    )

    _final_status = None
    while True:
        _resp = sandbox_get(f"/managed-runners/{runner_id}")
        _elapsed = _time.time() - _t0

        if _resp.status_code >= 300:
            _final_status = mo.callout(
                mo.md(
                    f"❌ HTTP {_resp.status_code}\n\n```\n{_resp.text[:400]}\n```"
                ),
                kind="danger",
            )
            break

        _body = _resp.json()
        _r = _body[0] if isinstance(_body, list) and _body else _body
        _install = (_r or {}).get("installStatus", "UNKNOWN")
        _connect = (_r or {}).get("connectionStatus", "UNKNOWN")
        _ready = "READY" in _install.upper() and "CONNECTED" in _connect.upper()

        if _ready:
            _final_status = mo.callout(
                mo.md(
                    f"✅ **Runner `{runner_id}` is READY + CONNECTED** "
                    f"(took {_elapsed:.0f}s)\n\n"
                    f"- install: **{_install}**\n- connection: **{_connect}**"
                ),
                kind="success",
            )
            break

        if _elapsed > _max_wait_s:
            _final_status = mo.callout(
                mo.md(
                    f"⚠️ Timed out after {_max_wait_s:.0f}s. Last state:\n\n"
                    f"- install: **{_install}**\n- connection: **{_connect}**\n\n"
                    "_Runner may still be starting up. Re-run this cell to keep polling._"
                ),
                kind="warn",
            )
            break

        mo.output.append(
            mo.md(
                f"  …+{_elapsed:.0f}s: install=`{_install}` "
                f"connection=`{_connect}`"
            )
        )
        _time.sleep(_poll_interval)

    _final_status
    return


# ----------------------------------------------------------------- #
# Step 3 — First sandbox via the Python SDK                         #
# ----------------------------------------------------------------- #
@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Step 3 — First sandbox (Python SDK)

    Launch a sandbox using the `default` profile binding on your
    runner, `exec` a shell command inside it, capture stdout, and stop
    the sandbox. End to end in 4 lines of Python.

    ```python
    from cwsandbox import Sandbox

    with Sandbox.run(profile_names=["default"]) as sb:
        result = sb.exec(["sh", "-c", "echo hello; uname -a"]).result()
        print(result.stdout)
    ```


    The SDK reads its credentials from the `CWSANDBOX_API_KEY` env var,
    which the Connect cell above set from your CW access token. No
    additional auth setup.
    """)
    return


@app.cell(hide_code=True)
def _():
    launch_sandbox_btn = mo.ui.run_button(label="Launch a sandbox and run echo", kind="success")
    launch_sandbox_btn
    return (launch_sandbox_btn,)


@app.cell(hide_code=True)
def _(cw_token: str | None, launch_sandbox_btn: mo.ui.run_button):
    mo.stop(not cw_token or not launch_sandbox_btn.value)

    import traceback

    try:
        with Sandbox.run(profile_names=["default"]) as _sb:
            _r = _sb.exec(["sh", "-c", "echo hello from inside the sandbox; uname -a"]).result()
        _output = mo.callout(
            mo.md(
                f"✅ **Sandbox executed.**\n\n```\n{_r.stdout}\n```\n\n"
                "_The `with` block called `stop()` on exit. The default command "
                "(`sleep infinity`) keeps the sandbox alive while you `exec` into it._"
            ),
            kind="success",
        )
    except Exception as _exc:
        _output = mo.callout(
            mo.md(
                f"❌ **Sandbox launch failed:** `{type(_exc).__name__}: {_exc}`\n\n"
                f"<details><summary>Full traceback</summary>\n\n```\n{traceback.format_exc()}\n```\n</details>\n\n"
                f"_Common causes: runner just deployed (gateway needs ~30s to sync), "
                f"profile name mismatch, or token lacks `SANDBOX_USER`._"
            ),
            kind="danger",
        )
    _output
    return


# ----------------------------------------------------------------- #
# Step 4 — Tool-calling agent loop                                  #
# ----------------------------------------------------------------- #
@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Step 4 — RL with verifiable rewards (parallel rewards)

     A model generates
    *N* candidate code completions. Each one runs in its own sandbox. The
    unit-test pass/fail of each completion is the reward signal. Training
    consumes the rewards in a policy update.

    **What this demo does** — five toy "model completions" (the kind of
    Python snippets a code-gen model would emit). Each is sent to its own
    sandbox. We use `cwsandbox.wait(pending, num_returns=1)` to **collect
    results as they complete** — so the fastest correct answers arrive
    first and slow / failing ones land later. This is the actual shape of
    an RL training step: launch a batch in parallel, harvest rewards as
    each sandbox finishes.

    """)
    return


@app.cell(hide_code=True)
def _():
    run_agent_btn = mo.ui.run_button(label="Run parallel reward eval (5 sandboxes)", kind="success")
    run_agent_btn
    return (run_agent_btn,)


@app.cell(hide_code=True)
def _(cw_token: str | None, run_agent_btn: mo.ui.run_button, wandb_token: str | None, weave_url: str | None):
    mo.stop(not cw_token or not run_agent_btn.value)

    import time as _time

    import cwsandbox
    from cwsandbox import Session, SandboxDefaults

    # Weave tracing — if the Connect cell initialized Weave, this decorator
    # records every score_completion() call. If Weave wasn't initialized
    # (no W&B token provided), @weave.op is a transparent no-op.
    @weave.op
    def score_completion(name: str, code: str, returncode: int, stdout: str, stderr: str) -> dict:
        """Compute reward from a sandbox execution. Decorated with @weave.op
        so the call is traced (inputs + output + latency) to your wandb run."""
        return {
            "name": name,
            "code": code,
            "returncode": returncode,
            "reward": 1.0 if returncode == 0 else 0.0,
            "stdout": stdout,
            "stderr": stderr,
        }

    # Five toy "model completions" — what a code-gen model might emit. A real
    # training pipeline would parse these out of model output via something
    # like extract_xml_answer() that pulls code from <answer>...</answer>.
    _COMPLETIONS = [
        {"name": "slow-sum",       "code": "print(sum(range(100_000)))"},
        {"name": "string-ops",     "code": "print('hello'[::-1])"},
        {"name": "delayed-error",  "code": "import time; time.sleep(0.5); raise ValueError('oops')"},
        {"name": "syntax-error",   "code": "print('missing parenthesis'"},
        {"name": "slow-list",      "code": "print(len([i*i for i in range(50_000)]))"},
    ]

    mo.output.append(mo.md(
        f"**Evaluating {len(_COMPLETIONS)} completions in parallel** — one sandbox each."
    ))

    _defaults = SandboxDefaults(
        container_image="python:3.11",
        tags=("workshop-rewards", "rl-training-demo"),
    )
    _t0 = _time.time()

    with Session(defaults=_defaults) as _session:
        # Launch all in parallel. session.sandbox() returns a sandbox handle;
        # .exec() kicks off the command and returns immediately with a Process.
        _processes = [
            (idx, c["name"], _session.sandbox().exec(
                ["python", "-c", c["code"]],
                timeout_seconds=15.0,
            ))
            for idx, c in enumerate(_COMPLETIONS)
        ]
        mo.output.append(mo.md(
            f"⏱️ Launched all {len(_processes)} sandboxes at +{_time.time() - _t0:.1f}s. "
            "Waiting for results to arrive…\n\n---"
        ))

        # Collect results as they complete (faster ones first). cwsandbox.wait
        # is the bit that makes this an RL inner loop — your trainer doesn't
        # have to block on the slowest rollout.
        _pending_handles = [p for _, _, p in _processes]
        _handle_to_meta = {id(p): (idx, name) for idx, name, p in _processes}
        _rewards: dict[int, tuple[str, float, str]] = {}

        _code_by_idx = {idx: c["code"] for idx, c in enumerate(_COMPLETIONS)}
        while _pending_handles:
            _done, _pending_handles = cwsandbox.wait(_pending_handles, num_returns=1)
            for _proc in _done:
                _idx, _name = _handle_to_meta[id(_proc)]
                try:
                    _r = _proc.result()
                    _scored = score_completion(
                        name=_name,
                        code=_code_by_idx[_idx],
                        returncode=_r.returncode,
                        stdout=_r.stdout or "",
                        stderr=_r.stderr or "",
                    )
                    _reward = _scored["reward"]
                    _short = (_scored["stdout"].strip() or _scored["stderr"].strip().splitlines()[-1] if _scored["stderr"].strip() else "")[:80]
                except Exception as _e:
                    _reward = 0.0
                    _short = f"{type(_e).__name__}: {_e}"[:80]
                _rewards[_idx] = (_name, _reward, _short)
                _icon = "✅" if _reward == 1.0 else "❌"
                _elapsed = _time.time() - _t0
                mo.output.append(mo.md(
                    f"  {_icon} **{_name}** — reward = `{_reward}` (arrived at +{_elapsed:.1f}s)  \n"
                    f"  &nbsp;&nbsp;&nbsp;output: `{_short}`"
                ))

    _total_time = _time.time() - _t0
    _total_reward = sum(r for _, r, _ in _rewards.values())

    # Final summary in original order
    _rows = ["| # | Completion | Reward | Output |", "|---|---|---|---|"]
    for _idx in sorted(_rewards.keys()):
        _name, _reward, _short = _rewards[_idx]
        _icon = "✅" if _reward == 1.0 else "❌"
        _rows.append(f"| {_idx} | `{_name}` | {_icon} {_reward} | `{_short}` |")
    _rows.append(
        f"\n**Total reward: {_total_reward} / {len(_COMPLETIONS)}** "
        f"({int(_total_reward / len(_COMPLETIONS) * 100)}%) · "
        f"**wall time {_total_time:.1f}s** across {len(_COMPLETIONS)} parallel sandboxes."
    )
    if wandb_token and weave_url:
        _rows.append(
            f"\n🔭 **Weave traces** — each `score_completion` call was logged. "
            f"[View dashboard]({weave_url})"
        )
    elif wandb_token:
        _rows.append(
            "\n🔭 **Weave traces** — each `score_completion` call was logged to your wandb account."
        )
    mo.output.append(mo.callout(mo.md("\n".join(_rows)), kind="success"))
    return


# ----------------------------------------------------------------- #
# Step 5 — Observability with Weave (pure docs, no upstream deps)    #
# ----------------------------------------------------------------- #
@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Step 5 — Observability with Weave

    [Weave](https://wandb.ai/site/weave/) is W&B's tracing layer for LLM and
    agent workloads. It records every decorated function call — inputs,
    outputs, latency, errors — and groups them into a UI you can drill into
    after the fact. For an RL or agentic-eval pipeline that means: for every
    completion you scored in Step 4, you can see exactly what code the model
    emitted, what the sandbox returned, how long it took, and whether the
    reward was 1 or 0.

    ### How to set it up (3 steps)

    1. **Get a W&B API key** at [wandb.ai/authorize](https://wandb.ai/authorize)
       (free tier is fine). If you already have a W&B account, this is just
       the access token from your profile.
    2. **Paste it into the Connect form above** as the second password
       field. The notebook stores it in `WANDB_API_KEY` and calls
       `weave.init("sandboxes-workshop")`, which authenticates with W&B and
       tags every traced call against the `sandboxes-workshop` project in
       your W&B entity.
    3. **Run Step 4.** The `score_completion()` function is decorated with
       `@weave.op`, so every parallel reward call gets logged automatically
       — inputs (completion name, code, sandbox output) and output (the
       reward dict). Latency is captured for free.

    ### View your dashboard

    After Step 4 runs with a W&B token set, your direct dashboard link
    appears in **two places**:

    - The **Connect callout** above (✅ Weave tracing enabled → [view
      dashboard])
    - The **Step 4 summary callout** (Weave traces → [view dashboard])

    You can also navigate manually: [wandb.ai](https://wandb.ai) → your
    entity → the `sandboxes-workshop` project → **Weave** tab on the left
    sidebar.

    ### What you'll see in Weave

    - **Calls** — one row per `score_completion()` invocation. Click any
      row to see the full inputs (the model's code), the captured
      stdout/stderr from the sandbox, the returncode, and the computed
      reward.
    - **Operations** — the `score_completion` op with aggregate stats:
      total calls, average reward, latency p50/p95.
    - **Filtering** — filter by reward (e.g. show only `reward=0.0` to
      debug failures), or by code substring, or by latency.
    """)
    return


# ----------------------------------------------------------------- #
# Step 6 — Cleanup                                                  #
# ----------------------------------------------------------------- #
@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Step 6 — Cleanup

    Tears down in the right order: runner → profile. Two explicit buttons
    because these are destructive — no auto-fire on cell re-execution.
    """)
    return


@app.cell(hide_code=True)   
def _():
    delete_runner_btn = mo.ui.run_button(label="🗑️ Delete runner", kind="danger")
    delete_profile_btn = mo.ui.run_button(label="🗑️ Delete profile", kind="danger")
    mo.vstack([delete_runner_btn, delete_profile_btn])
    return delete_profile_btn, delete_runner_btn


@app.cell(hide_code=True)
def _(
    cw_token: str | None,
    delete_runner_btn: mo.ui.run_button,
    runner_id: str,
    sandbox_delete,
):
    mo.stop(not cw_token or not delete_runner_btn.value)
    _r = sandbox_delete(f"/managed-runners/{runner_id}")
    _ok = _r.status_code < 300
    mo.callout(
        mo.md(f"{'✅' if _ok else '❌'} runner delete: HTTP {_r.status_code} — `{_r.text[:200]}`"),
        kind="success" if _ok else "danger",
    )
    return


@app.cell(hide_code=True)
def _(
    cw_token: str | None,
    delete_profile_btn: mo.ui.run_button,
    profile_id: str | None,
    sandbox_delete,
):
    mo.stop(not cw_token or not delete_profile_btn.value)
    mo.stop(not profile_id, mo.md("_No profile ID — Step 1 never succeeded._"))
    _r = sandbox_delete(f"/profile-templates/{profile_id}")
    _ok = _r.status_code < 300
    mo.callout(
        mo.md(f"{'✅' if _ok else '❌'} profile delete: HTTP {_r.status_code} — `{_r.text[:200]}`"),
        kind="success" if _ok else "danger",
    )
    return


# ----------------------------------------------------------------- #
# Outro                                                             #
# ----------------------------------------------------------------- #
@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## What you just did

    - Authored a profile template from a reactive form
    - Deployed a managed runner onto a CKS cluster
    - Launched a sandbox from the Python SDK
    - Ran a parallel reward-evaluation batch — the inner loop of RL with verifiable rewards
    - Cleaned up

    ## Where to next

    - [About CW Sandboxes](https://docs.coreweave.com/products/sandboxes)
    - [Architecture deep-dive](https://docs.coreweave.com/products/sandboxes/architecture)
    - [Python client guides](https://docs.coreweave.com/products/sandboxes/client)
    - [RL training patterns](https://docs.coreweave.com/products/sandboxes/client/guides/rl-training)
    - [Profile examples (5 patterns)](https://docs.coreweave.com/products/sandboxes/profiles/profile-examples)
    """)
    return


if __name__ == "__main__":
    app.run()
