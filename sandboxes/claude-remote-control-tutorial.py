# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "anywidget>=0.9",
#     "marimo>=0.23.6",
#     "wandb[sandbox]>=0.28.1",
# ]
# ///

import marimo

__generated_with = "0.23.15"
app = marimo.App(
    width="medium",
    app_title="Run Claude Code in a Remote Sandbox Environment",
    auto_download=["html"],
)


@app.cell
def _():
    import os
    import re
    import time

    import anywidget
    import marimo as mo
    import requests

    os.environ.setdefault("WANDB_SILENT", "true")

    from wandb.sandbox import (
        NetworkOptions,
        ResourceOptions,
        Sandbox,
        SandboxDefaults,
    )

    return (
        NetworkOptions,
        ResourceOptions,
        Sandbox,
        SandboxDefaults,
        anywidget,
        mo,
        os,
        re,
        requests,
        time,
    )


@app.cell
def _():
    # Survives relaunches of the sign-in step (this cell has no button
    # dependency, so it runs once). Holds the previous PTY session and its
    # state dict so a second "Start sign-in" press can tear the old one down
    # instead of leaking another `claude` process + pump thread into the
    # sandbox. That leak made repeated runs flaky.
    launch_registry: dict = {"session": None, "state": None}
    return (launch_registry,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Run Claude Code in a Remote Sandbox Environment

    /// admonition | What this notebook does
        type: info

    Claude Code runs inside a CoreWeave **Serverless Sandbox**, and you steer it
    from [claude.ai/code](https://claude.ai/code) or the Claude mobile app via
    **Remote Control**. Your laptop is only the interface; execution stays in the
    sandbox, inference stays on Anthropic's API.

    You need a [claude.ai](https://claude.ai/) subscription
    (Pro/Max/Team/Enterprise) for the sign-in step.
    ///

    /// admonition | Why a sandbox instead of the default cloud environment
        type: note

    Claude Code's built-in cloud environment is a locked-down, repo-only VM. Your
    own sandbox lets Claude do what that environment can't:

    - **Reach your tools and infrastructure.** Run inside your org's network to
      hit internal services, private registries, databases, and clusters.
    - **Use real compute.** GPUs and large CPU or memory for training, inference,
      or heavy builds.
    - **Host on a public URL.** Public ingress makes a dev server Claude starts
      reachable on the internet. The default environment only produces a PR, it
      can't expose a running site.
    - **Bring a custom environment.** Your own image, mounted data, and config.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    wandb_key_form = (
        mo.md("{api_key}")
        .batch(
            api_key=mo.ui.text(
                kind="password",
                placeholder="W&B API key from wandb.ai/authorize",
                full_width=True,
            ),
        )
        .form(submit_button_label="Connect", bordered=False)
    )
    mo.vstack(
        [
            mo.md(r"""
            ---
            ## 1. Connect W&B

            Paste your W&B API key from
            [wandb.ai/authorize](https://wandb.ai/authorize). It authenticates
            every `Sandbox` call in this notebook, starting with `Sandbox.run()`
            in the next step.
            """),
            wandb_key_form,
        ]
    )
    return (wandb_key_form,)


@app.cell(hide_code=True)
def _(mo, os, requests, wandb_key_form):
    form_value = wandb_key_form.value or {}
    candidate_key = form_value.get("api_key", "").strip()
    mo.stop(not candidate_key, mo.md("_Paste your API key above and press **Connect**._"))

    # Validate against the W&B API before exporting anything. This is the same
    # check `wandb login --verify` performs, minus its side effect of writing
    # the (possibly wrong) key to ~/.netrc before verifying it.
    with mo.status.spinner(title="Validating key with api.wandb.ai..."):
        viewer_resp = requests.post(
            "https://api.wandb.ai/graphql",
            json={"query": "query Viewer { viewer { username } }"},
            auth=("api", candidate_key),
            timeout=15,
        )
    viewer = (viewer_resp.json().get("data") or {}).get("viewer") if viewer_resp.ok else None
    mo.stop(
        not (viewer and viewer.get("username")),
        mo.callout(
            mo.md("❌ api.wandb.ai rejected this key. Copy it again from [wandb.ai/authorize](https://wandb.ai/authorize)."),
            kind="danger",
        ),
    )

    WANDB_KEY = candidate_key
    os.environ["WANDB_API_KEY"] = WANDB_KEY
    mo.callout(mo.md(f"✅ Key verified. Connected as **{viewer['username']}**."), kind="success")
    return (WANDB_KEY,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 2. Create the sandbox

    Pick a lifetime and press **Create sandbox** to call
    `Sandbox.run(..., max_lifetime_seconds=...)`.
    - The lifetime is a hard cap: it
    can't be extended later, and expiry kills the sandbox without preserving files.
    - `NetworkOptions(egress_mode="internet", ingress_mode="public", exposed_ports=(8080,))`
    gives it internet egress plus public ingress on **port 8080**, so anything
    Claude serves there is reachable straight from your browser (used in step 6).
    """)
    return


@app.cell
def _(ResourceOptions, SandboxDefaults):
    SANDBOX_DEFAULTS = SandboxDefaults(
        container_image="node:22",
        tags=("claude-code", "remote-control", "tutorial"),
        resources=ResourceOptions(requests={"cpu": "2", "memory": "4Gi"}),
    )
    return (SANDBOX_DEFAULTS,)


@app.cell(hide_code=True)
def _(mo):
    lifetime_slider = mo.ui.slider(
        start=1, stop=12, step=1, value=4,
        label="Sandbox lifetime (hours)",
        show_value=True,
    )
    create_btn = mo.ui.run_button(label="Create sandbox", kind="success")
    mo.hstack([lifetime_slider, create_btn], justify="start", gap=2)
    return create_btn, lifetime_slider


@app.cell
def _(
    NetworkOptions,
    SANDBOX_DEFAULTS,
    Sandbox,
    WANDB_KEY,
    create_btn,
    lifetime_slider,
    mo,
):
    assert WANDB_KEY  # step 1 must be done first
    mo.stop(not create_btn.value, mo.md("_Press **Create sandbox** to provision the sandbox._"))

    lifetime_hours = lifetime_slider.value
    with mo.status.spinner(title="Creating sandbox..."):
        sandbox = Sandbox.run(
            defaults=SANDBOX_DEFAULTS,
            network=NetworkOptions(
                egress_mode="internet",
                ingress_mode="public",
                exposed_ports=(8080,),
            ),
            max_lifetime_seconds=int(lifetime_hours * 3600),
        )
        sandbox.wait()

    service_note = (
        f" Port 8080 is public at **`{sandbox.service_address}`**."
        if sandbox.service_address
        else ""
    )
    mo.callout(
        mo.md(
            f"✅ Sandbox **`{sandbox.sandbox_id}`** is running, hard expiry in "
            f"**{lifetime_hours}h**.{service_note}"
        ),
        kind="success",
    )
    return (sandbox,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 3. Install Claude Code

    `sandbox.exec(...)` runs one command that installs Claude Code via npm and
    pre-writes `~/.claude.json` so `/workspace` is already trusted.
    """)
    return


@app.cell
def _(mo, sandbox):
    CLAUDE_JSON = '{"hasCompletedOnboarding": true, "projects": {"/workspace": {"hasTrustDialogAccepted": true}}}'
    BOOTSTRAP_CMD = (
        "npm install -g @anthropic-ai/claude-code --silent "
        "&& mkdir -p /workspace "
        f"&& printf '%s' '{CLAUDE_JSON}' > ~/.claude.json"
    )

    with mo.status.spinner(title="Installing Claude Code in the sandbox (~30-60s)..."):
        bootstrap_proc = sandbox.exec(["bash", "-lc", BOOTSTRAP_CMD], timeout_seconds=900)
        bootstrap_proc.wait(timeout=900)

    bootstrap_ok = bootstrap_proc.returncode == 0
    if bootstrap_ok:
        bootstrap_note = mo.callout(mo.md("✅ Claude Code installed and `/workspace` pre-trusted."), kind="success")
    else:
        bootstrap_stderr = bootstrap_proc.result().stderr_bytes.decode(errors="replace")
        bootstrap_note = mo.callout(
            mo.md(f"❌ Bootstrap failed:\n\n```\n{bootstrap_stderr[-1500:]}\n```"),
            kind="danger",
        )
    bootstrap_note
    return (bootstrap_ok,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 4. Sign in and start Remote Control

    Remote Control only accepts a full claude.ai login (API keys and setup-tokens
    are rejected), so `sandbox.shell(...)` opens a PTY running
    `claude auth login && cd /workspace && exec claude remote-control --name
    'CoreWeave Sandboxes'`. The `--name` flag is what titles the session in
    claude.ai/code; change that string to rename it. Only two steps need you:

    1. Open the **authorization link** when it appears in the banner and approve.
    2. Paste the returned code into the box and press **Submit code**.

    When the banner turns green it pins the **session link** and the Remote
    Control details right there in the panel, so they stay put instead of
    scrolling away. Step 5 explains exactly what to do with them.

    The panel refreshes itself every couple of seconds during sign-in and stops
    once Remote Control is up. If something gets stuck, the raw sandbox console and
    manual keys are in the collapsible section at the bottom. Pressing **Start
    sign-in + Remote Control** again cleanly restarts the session (it stops the
    previous one first).
    """)
    return


@app.cell(hide_code=True)
def _(anywidget, mo):
    class NotificationSilencer(anywidget.AnyWidget):
        """Invisible widget that stubs the browser Notification API.

        marimo fires a desktop notification every time a run completes while
        the tab is unfocused, and the auto-refresh console below completes a
        run every couple of seconds. marimo has no setting to turn this off
        (v0.23), but its code bails out when Notification.permission is
        "denied", so this widget replaces window.Notification with a stub
        that always reports "denied". Applies to this notebook page only.
        """

        _esm = """
        function render({ el }) {
          class SilentNotification {
            static get permission() { return "denied"; }
            static requestPermission() { return Promise.resolve("denied"); }
          }
          window.Notification = SilentNotification;
          el.style.display = "none";
        }
        export default { render };
        """

    notification_silencer = mo.ui.anywidget(NotificationSilencer())
    notification_silencer
    return


@app.cell(hide_code=True)
def _(bootstrap_ok, mo):
    mo.stop(not bootstrap_ok, mo.md("_Fix the bootstrap above first._"))
    launch_btn = mo.ui.run_button(label="Start sign-in + Remote Control", kind="success")
    launch_btn
    return (launch_btn,)


@app.cell(hide_code=True)
def _(launch_btn, launch_registry, mo, re, sandbox):
    mo.stop(not launch_btn.value, mo.md("_Press the button to open the PTY session in the sandbox._"))

    # Relaunch cleanup: stop the previous session's Remote Control server and
    # signal its pump thread to exit, so we never run two `claude` PTYs at once.
    prev_session = launch_registry.get("session")
    prev_state = launch_registry.get("state")
    if prev_session is not None:
        if prev_state is not None:
            prev_state["ended"] = True
        try:
            prev_session.stdin.write(b"\x03").result()  # Ctrl-C the old claude
        except Exception:  # noqa: BLE001 - old PTY may already be gone
            pass

    RUN_CMD = (
        "claude auth login && cd /workspace "
        "&& exec claude remote-control --name 'CoreWeave Sandboxes'"
    )
    output_chunks: list[bytes] = []
    # Holds the last response to a submitted code so the callout survives
    # panel re-renders.
    feedback_store: dict = {}
    # Flipped by the pump thread when the PTY closes (e.g. after Ctrl-C), so
    # the panel stops writing to a dead stream.
    session_state = {"ended": False}
    # A very wide PTY keeps long OAuth / session URLs on a single line.
    session = sandbox.shell(["bash", "-lc", RUN_CMD], width=500, height=40)

    ANSI_RE = re.compile(
        rb"\x1b\[[0-9;?]*[ -/]*[@-~]"  # CSI sequences (colors, cursor movement)
        rb"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC sequences (titles, links)
        rb"|\x1b[@-_]"  # other escapes
    )

    def render_output(chunks: list[bytes], max_lines: int = 40) -> str:
        text = ANSI_RE.sub(b"", b"".join(chunks)).decode("utf-8", errors="replace")
        lines = []
        for raw_line in text.split("\n"):
            # PTYs end lines with \r\n: drop the trailing \r, then keep only
            # the text after any remaining \r (in-place TUI redraws).
            line = raw_line.rstrip("\r")
            lines.append(line.rsplit("\r", 1)[-1])
        return "\n".join(lines[-max_lines:])

    def find_urls(chunks: list[bytes]) -> list[str]:
        # Scan the RAW stream: links can arrive inside OSC-8 hyperlink escapes,
        # which ANSI stripping would delete.
        raw_text = b"".join(chunks).decode("utf-8", errors="replace")
        urls: list[str] = []
        for raw_url in re.findall(r"https://[^\s\x1b\x07\"'`]+", raw_text):
            url = raw_url.rstrip(").,;|>")
            if url not in urls and ("claude.ai" in url or "claude.com" in url):
                urls.append(url)
        return urls

    def pump_session_output() -> None:
        # Both interactive prompts in this flow have fixed answers, so the pump
        # answers them itself: Enter picks the (pre-selected) claude.ai option
        # at the login menu, and "y" confirms the "Enable Remote Control?"
        # prompt. The only human steps left are opening the authorization link
        # and pasting the code back.
        thread = mo.current_thread()
        auto_answered = {"login_menu": False, "enable_rc": False}
        try:
            for chunk in session.output:
                # marimo sets should_exit when this cell is re-run, interrupted,
                # or the kernel is restarted. Bail so the thread doesn't outlive
                # its session and desync the frontend. (The relaunch teardown
                # above Ctrl-Cs the old PTY, which unblocks this read so the
                # check is reached promptly.)
                if thread.should_exit:
                    break
                output_chunks.append(chunk)
                text = b"".join(output_chunks).decode("utf-8", errors="replace")
                if not auto_answered["login_menu"] and "login method" in text.lower():
                    auto_answered["login_menu"] = True
                    session.stdin.write(b"\r").result()
                if not auto_answered["enable_rc"] and "Enable Remote Control?" in text:
                    auto_answered["enable_rc"] = True
                    session.stdin.write(b"y\r").result()
        except Exception:  # noqa: BLE001 - session closing is the normal exit path
            pass
        finally:
            session_state["ended"] = True

    # mo.Thread, not threading.Thread: marimo tracks it across re-runs and kernel
    # restarts and signals should_exit on invalidation. A raw thread survives a
    # restart orphaned, which is what left the panel broken until a full page
    # reload (Cmd+R). Requires marimo >= 0.23.
    mo.Thread(target=pump_session_output, daemon=True).start()
    launch_registry["session"] = session
    launch_registry["state"] = session_state
    return (
        feedback_store,
        find_urls,
        output_chunks,
        render_output,
        session,
        session_state,
    )


@app.cell(hide_code=True)
def _(mo, session):
    assert session is not None  # console pairs with the live session
    # Rendered invisibly by the panel below, and only until sign-in completes.
    console_refresh = mo.ui.refresh(default_interval="2s")
    key_input = mo.ui.text(placeholder="paste the authorization code here", full_width=True)
    send_btn = mo.ui.run_button(label="Submit code", kind="success")
    enter_btn = mo.ui.run_button(label="Enter")
    up_btn = mo.ui.run_button(label="↑")
    down_btn = mo.ui.run_button(label="↓")
    ctrl_c_btn = mo.ui.run_button(label="Ctrl-C", kind="danger")
    return (
        console_refresh,
        ctrl_c_btn,
        down_btn,
        enter_btn,
        key_input,
        send_btn,
        up_btn,
    )


@app.cell(hide_code=True)
def _(
    console_refresh,
    ctrl_c_btn,
    down_btn,
    enter_btn,
    feedback_store: dict,
    find_urls,
    key_input,
    mo,
    output_chunks: list[bytes],
    render_output,
    send_btn,
    session,
    session_state,
    time,
    up_btn,
):
    console_refresh.value  # re-render on each invisible tick (while sign-in runs)

    keystrokes = b""
    if send_btn.value:
        keystrokes = key_input.value.encode() + b"\r"
    elif enter_btn.value:
        keystrokes = b"\r"
    elif up_btn.value:
        keystrokes = b"\x1b[A"
    elif down_btn.value:
        keystrokes = b"\x1b[B"
    elif ctrl_c_btn.value:
        keystrokes = b"\x03"

    if keystrokes and not session_state["ended"]:
        chunk_mark = len(output_chunks)
        try:
            session.stdin.write(keystrokes).result()
        except Exception:  # noqa: BLE001 - PTY closed between check and write
            session_state["ended"] = True
        if send_btn.value and not session_state["ended"]:
            # Wait for the sandbox to process the pasted code, then persist its
            # full response, success or error, so the callout survives
            # later re-renders.
            with mo.status.spinner(title="Submitting code to the sandbox..."):
                time.sleep(6)
            response_text = render_output(output_chunks[chunk_mark:], max_lines=200).strip()
            response_lower = response_text.lower()
            has_error = any(w in response_lower for w in ("error", "invalid", "failed", "expired", "denied"))
            has_success = any(w in response_lower for w in ("success", "logged in", "welcome"))
            feedback_store["kind"] = "danger" if has_error else ("success" if has_success else "info")
            feedback_store["text"] = response_text or "(no output captured, check the console below)"

    console_text = render_output(output_chunks) or "(waiting for output...)"
    full_text = b"".join(output_chunks).decode("utf-8", errors="replace")
    detected_urls = find_urls(output_chunks)
    authorize_url = next((u for u in detected_urls if "oauth" in u or "authorize" in u), None)
    rc_session_url = next((u for u in detected_urls if "/code/" in u), None)
    rc_policy_blocked = "Remote Control is disabled" in full_text
    signed_in = "Login successful" in full_text
    session_ended = session_state["ended"]

    # Once the session URL appears, keep refreshing a few more ticks so the rest
    # of the Remote Control banner (the "how to connect" instructions) finishes
    # printing, then snapshot it into feedback_store. Stored there, it survives
    # every later re-render instead of flashing once and vanishing.
    if rc_session_url:
        feedback_store["rc_ticks"] = feedback_store.get("rc_ticks", 0) + 1
        feedback_store["remote_control_output"] = render_output(output_chunks, max_lines=200).strip()
    rc_settled = feedback_store.get("rc_ticks", 0) >= 3
    flow_done = (bool(rc_session_url) and rc_settled) or rc_policy_blocked or session_ended

    if session_ended:
        status = mo.callout(
            mo.md(
                "⚪ **The sandbox session has ended** (Remote Control stopped). Press "
                "**Start sign-in + Remote Control** above to relaunch, or continue to **Clean up**."
            ),
            kind="warn",
        )
    elif rc_session_url:
        status = mo.callout(
            mo.md(
                f"🟢 **Remote Control is live.** [Open your session ↗]({rc_session_url}), "
                f"or find it under **Code** in the Claude mobile app."
            ),
            kind="success",
        )
    elif rc_policy_blocked:
        status = mo.callout(
            mo.md(
                "❌ **Signed in, but your organization has Remote Control disabled.** "
                "On Team and Enterprise plans it's off by default, an Owner must enable the "
                "**Remote Control** toggle at "
                "[claude.ai/admin-settings/claude-code](https://claude.ai/admin-settings/claude-code), "
                "then restart this step."
            ),
            kind="danger",
        )
    elif signed_in:
        status = mo.callout(
            mo.md("✅ **Signed in.** Enabling Remote Control automatically, the session link will appear here in a moment..."),
            kind="info",
        )
    elif authorize_url:
        status = mo.callout(
            mo.md(
                f"🔑 **Sign in:** [open the authorization page ↗]({authorize_url}), approve, "
                f"then paste the returned code below and press **Submit code**."
            ),
            kind="info",
        )
    else:
        status = mo.callout(
            mo.md("⏳ Starting sign-in. The login menu is answered automatically; the authorization link will appear here."),
            kind="neutral",
        )

    panel_items = [status]
    if feedback_store.get("remote_control_output"):
        # Persisted so the "how to connect" text stays put after the panel
        # freezes. Previously it flashed once and was gone.
        panel_items.append(
            mo.callout(
                mo.vstack(
                    [
                        mo.md("**Remote Control session details (kept here for reference):**"),
                        mo.plain_text(feedback_store["remote_control_output"]),
                    ]
                ),
                kind="success",
            )
        )
    if feedback_store.get("text"):
        panel_items.append(
            mo.callout(
                mo.vstack(
                    [
                        mo.md("**Sandbox response to the submitted code:**"),
                        mo.plain_text(feedback_store["text"]),
                    ]
                ),
                kind=feedback_store["kind"],
            )
        )
    if authorize_url and not signed_in and not flow_done:
        # The code box only matters between "link surfaced" and "signed in".
        panel_items.append(mo.hstack([key_input, send_btn], widths=[5, 1], gap=0.5))
    panel_items.append(
        mo.accordion(
            {
                "Raw sandbox console + manual keys": mo.vstack(
                    [
                        mo.plain_text(console_text),
                        mo.hstack([enter_btn, up_btn, down_btn, ctrl_c_btn], justify="start", gap=0.5),
                    ]
                )
            }
        )
    )
    if not flow_done:
        # The invisible refresh only renders (and therefore only ticks) while
        # sign-in is still in progress; once Remote Control is live or blocked,
        # it drops out of the output and the auto-refresh stops for good.
        panel_items.append(mo.Html(f"<div style='display:none'>{console_refresh}</div>"))
    mo.vstack(panel_items)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 5. Use your new remote environment

    With the banner green, the sandbox is now hosting a **Remote Control session**
    registered to your claude.ai account. It appears anywhere you're signed in,
    marked with a computer icon and a green status dot. The sandbox does the work;
    every surface below is just a window into it. You can drive it from all three
    at once, messages, subagent progress, and files stay in sync.

    ### From the web (claude.ai/code)

    1. Click the **session link** in the green banner above, or open
       [claude.ai/code](https://claude.ai/code) and pick it out of the list by
       name. It shows up as **CoreWeave Sandboxes** (set with `--name` on the
       `claude remote-control` command in step 4; change that string to rename it,
       or run `/rename` in the session). Online sessions show a computer icon with
       a green dot.
    2. Type a prompt. It runs **inside the sandbox**, against the sandbox
       filesystem, and `@` autocompletes paths from `/workspace`.

    ### From your phone (the Claude app)

    1. Install the Claude app for [iOS](https://apps.apple.com/us/app/claude-by-anthropic/id6473753684)
       or [Android](https://play.google.com/store/apps/details?id=com.anthropic.claude)
       and sign in with the **same** account.
    2. Tap **Code** in the bottom navigation to reach the session list, then open
       the session with the green dot. (No app yet? Run `/mobile` in a terminal
       Claude Code session for a download QR code.)
    3. Approve tool calls and send follow-ups from anywhere. Ask "notify me when
       the build finishes" and a long turn will push to your phone.

    This notebook already started the host process for you: inside the sandbox it
    ran `claude remote-control` (server mode), which is what registered the
    session. There is nothing extra to run to use *this* sandbox, connect from the
    web or phone above.

    /// admonition | `/teleport` runs on *your* machine, not the sandbox
        type: warning

    claude.ai/code offers an **Open in terminal** button that copies a
    `claude --teleport <session-id>` command. Running it does **not** attach your
    terminal to the sandbox, it forks the conversation into a **new local session
    on your laptop**, seeded with a copy of the transcript. Execution and
    filesystem then belong to your laptop (ask for `hostname` and you'll see your
    laptop, while claude.ai/code still reports the sandbox). The two sessions
    diverge from that point, local work won't appear in the app. Only the
    transcript travels; the host machine never does. To keep working *in the
    sandbox*, steer it from claude.ai/code or mobile, or open another
    `sandbox.shell(...)` into it, don't teleport.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 6. Try it: have Claude build a live website

    Remote Control is running, so switch to [claude.ai/code](https://claude.ai/code)
    (or the **Code** tab in the mobile app), open your session, and paste the
    prompt below, it already contains this sandbox's public address (read from
    `sandbox.service_address`). Claude will build the site inside the sandbox and
    serve it on port 8080; open the link when it reports done.
    """)
    return


@app.cell(hide_code=True)
def _(mo, sandbox, session):
    assert session is not None  # meaningful only once Remote Control is running

    if sandbox.service_address:
        site_url = f"http://{sandbox.service_address}"
        demo_prompt = (
            "Build me a sample website and give me a link to access it. Make it a \n"
            "landing page for the concept of running a W&B Serverless Sandbox as a \n"
            "remote environment for Claude Code. Add some cool design elements and \n"
            "animations, and make sure actual logos are present for both Weights & Biases \n"
            "and Claude. Serve it on port 8080, bound to 0.0.0.0, and keep the \n"
            "server running. Port 8080 on this machine is publicly reachable at \n"
            f"{site_url}. Once the server is up, give me that direct link to \n"
            "access the site."
        )
        demo_out = mo.vstack(
            [
                mo.md(f"```text\n{demo_prompt}\n```"),
                mo.md(f"Once Claude reports the server is running, the site is at [{site_url}]({site_url})."),
            ]
        )
    else:
        demo_out = mo.callout(
            mo.md(
                "⚠️ This sandbox has no public service address, the runner may not "
                "support `ingress_mode=\"public\"`. Recreate the sandbox in step 2 "
                "or ask your W&B admin about ingress support."
            ),
            kind="warn",
        )
    demo_out
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 7. Clean up

    The sandbox bills until you stop it or the lifetime expires. Ctrl-C above stops the Remote Control server; the button below calls
    `sandbox.stop()`. Lost sandboxes: `Sandbox.list(tags=["remote-control"]).result()`.
    """)
    return


@app.cell(hide_code=True)
def _(mo, sandbox):
    assert sandbox is not None  # nothing to stop before creation
    stop_btn = mo.ui.run_button(label="Stop sandbox", kind="danger")
    stop_btn
    return (stop_btn,)


@app.cell
def _(mo, sandbox, stop_btn):
    mo.stop(not stop_btn.value, mo.md("_Press **Stop sandbox** when you're finished._"))
    sandbox.stop(missing_ok=True).result()
    mo.callout(mo.md(f"✅ Sandbox `{sandbox.sandbox_id}` stopped."), kind="success")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    /// details | Where to next
        type: info

    - [`claude-remote-control-script.py`](https://github.com/coreweave/reference-architecture/blob/main/sandboxes/claude-remote-control-script.py):
      the compact terminal version of this notebook — attach your real terminal
      to a PTY in the sandbox and sign in from there
    - [Remote Control docs](https://code.claude.com/docs/en/remote-control)
    - [Sandbox environments compared](https://code.claude.com/docs/en/sandbox-environments)
    ///
    """)
    return


if __name__ == "__main__":
    app.run()
