# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo>=0.23.6",
#     "wandb[sandbox]>=0.28.1",
# ]
# ///

import marimo

__generated_with = "0.23.14"
app = marimo.App(
    width="medium",
    app_title="Devin Outpost on CW Serverless Sandboxes",
    css_file="/usr/local/_marimo/custom.css",
    auto_download=["html"],
)


@app.cell
def _():
    import os
    import time
    from pathlib import Path

    import marimo as mo
    from wandb.sandbox import (
        NetworkOptions,
        ResourceOptions,
        Sandbox,
        SandboxDefaults,
    )

    return (
        NetworkOptions,
        Path,
        ResourceOptions,
        Sandbox,
        SandboxDefaults,
        mo,
        os,
        time,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                r"""
                # Run a Devin Outpost on CW Serverless Sandboxes

                /// admonition | About This Notebook
                    type: info

                This tutorial connects a single
                [CW Serverless Sandbox](https://docs.wandb.ai/sandboxes)
                to a Devin Outpost. You create the Linux Outpost in Devin Cloud,
                paste the token shown at creation, and launch an isolated worker
                from Devin's official CLI image.

                _If you are running this notebook in edit mode, start by running all cells._
                ///
                """
            ),
            mo.md(
                r"""
                /// details | Table of Contents
                    type: info

                - [**Create a Devin Outpost**](#1-create-a-devin-outpost)
                - [**Connect credentials**](#2-connect-credentials)
                - [**Start the worker**](#3-start-the-worker)
                - [**Start a Devin session**](#4-start-a-devin-session)
                - [**Clean up**](#5-clean-up)
                ///
                """
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 1. Create a Devin Outpost

    In [Devin Cloud](https://app.devin.ai), open
    **Settings → Environment → Outposts**, select **Create Outpost**, give it
    a name, and choose **Linux** as the platform.

    Devin shows the Outpost token once. Copy it and keep it secure; the
    notebook asks for it in the next section. For the authoritative setup
    steps and current prerequisites, see the
    [Devin Outposts quickstart](https://docs.devin.ai/cloud/outposts/quickstart).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 2. Connect credentials

    Enter the W&B key used to create CW Serverless Sandboxes, plus the Outpost
    name and token shown when you created it. Both secrets are masked, and
    the Outpost token is passed to the worker through an environment variable
    instead of being embedded in its command text.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    credentials_form = (
        mo.md(
            """
            - W&B API key: {wandb_api_key}
            - Devin Outpost name: {outpost_name}
            - Devin Outpost token: {outpost_token}
            """
        )
        .batch(
            wandb_api_key=mo.ui.text(
                kind="password",
                placeholder="from wandb.ai/authorize",
                full_width=True,
            ),
            outpost_name=mo.ui.text(
                placeholder="my-linux-outpost",
                full_width=True,
            ),
            outpost_token=mo.ui.text(
                kind="password",
                placeholder="shown once when the Outpost is created",
                full_width=True,
            ),
        )
        .form(submit_button_label="Launch worker", bordered=True)
    )
    credentials_form
    return (credentials_form,)


@app.cell(hide_code=True)
def _(credentials_form, mo, os):
    credentials = credentials_form.value or {}
    WANDB_API_KEY = credentials.get("wandb_api_key")
    DEVIN_OUTPOST_NAME = credentials.get("outpost_name")
    DEVIN_OUTPOST_TOKEN = credentials.get("outpost_token")

    mo.stop(
        not (WANDB_API_KEY and DEVIN_OUTPOST_NAME and DEVIN_OUTPOST_TOKEN),
        mo.md("_Fill in all three fields and press **Launch worker**._"),
    )

    os.environ["WANDB_API_KEY"] = WANDB_API_KEY
    return DEVIN_OUTPOST_NAME, DEVIN_OUTPOST_TOKEN


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 3. Start the worker

    The sandbox uses Devin's official CLI image and installs `git`, the
    required developer tool from Devin's container quickstart. Internet
    egress lets the worker reach Devin and external package registries.

    This example keeps one worker alive for at most one hour. For repeated
    use, bake your repositories and development tools into a dedicated
    image instead of installing them at startup.
    """)
    return


@app.cell
def _(
    DEVIN_OUTPOST_NAME,
    DEVIN_OUTPOST_TOKEN,
    NetworkOptions,
    ResourceOptions,
    Sandbox,
    SandboxDefaults,
    mo,
    time,
):
    defaults = SandboxDefaults(
        container_image="public.ecr.aws/e0h8a4b6/devin-cli:stable",
        tags=("devin-outpost", "tutorial"),
        environment_variables={
            "DEVIN_OUTPOST_NAME": DEVIN_OUTPOST_NAME,
            "DEVIN_OUTPOST_TOKEN": DEVIN_OUTPOST_TOKEN,
        },
        resources=ResourceOptions(
            requests={"cpu": "1", "memory": "2Gi"},
            limits={"cpu": "2", "memory": "4Gi"},
        ),
    )

    sandbox = Sandbox.run(
        defaults=defaults,
        network=NetworkOptions(egress_mode="internet"),
        max_lifetime_seconds=3600,
    )

    setup = sandbox.exec(
        [
            "bash",
            "-lc",
            (
                "apt-get update && "
                "apt-get install -y --no-install-recommends ca-certificates git && "
                "rm -rf /var/lib/apt/lists/* && "
                "mkdir -p /repos"
            ),
        ],
        timeout_seconds=300,
    ).result()
    mo.stop(
        setup.returncode != 0,
        mo.callout(
            mo.md(f"Worker setup failed with exit code `{setup.returncode}`."),
            kind="danger",
        ),
    )

    worker_process = sandbox.exec(
        [
            "bash",
            "-lc",
            (
                'exec devin worker start --outpost="$DEVIN_OUTPOST_NAME" '
                '--token="$DEVIN_OUTPOST_TOKEN"'
            ),
        ],
        cwd="/repos",
    )
    time.sleep(2)
    worker_returncode = worker_process.poll()
    mo.stop(
        worker_returncode is not None,
        mo.callout(
            mo.md(
                f"Devin worker exited during startup with code `{worker_returncode}`."
            ),
            kind="danger",
        ),
    )

    mo.callout(
        mo.md(
            f"🟢 Worker launched in sandbox `{sandbox.sandbox_id}`. "
            "In Devin Cloud, start a session and choose this Outpost under "
            "**Configuration → Virtual environment**."
        ),
        kind="success",
    )
    return (sandbox,)


@app.cell(hide_code=True)
def _(Path, mo):
    screenshot_path = "sandboxes/assets/image.png"
    mo.vstack(
        [
            mo.md(f"""
            ---
            ## 4. Start a Devin session

            In Devin Cloud, start a
            new **Agent** session, open **Virtual environment**, expand
            **Outposts**, and select **CW Serverless Sandbox**. Then enter a
            small prompt such as `Create a "hello world" python script for me`
            to confirm the session is running in the remote environment.
            """),
            mo.image(
                src=screenshot_path,
                alt=(
                    "Devin session composer with Virtual environment open and "
                    "CW Serverless Sandbox selected under Outposts"
                ),
                width="50%",
                rounded=True,
                caption=(
                    "Choose the CW Serverless Sandbox Outpost before submitting "
                    "your first prompt."
                ),
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 5. Clean up

    The worker and sandbox consume resources while they are active. Stop the
    sandbox when you finish the tutorial; it will also stop automatically
    after its one-hour maximum lifetime.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    stop_button = mo.ui.run_button(label="🛑 Stop sandbox")
    stop_button
    return (stop_button,)


@app.cell
def _(mo, sandbox, stop_button):
    mo.stop(
        not stop_button.value,
        mo.md("_Click **Stop sandbox** when you are finished._"),
    )
    sandbox.stop(missing_ok=True).result()
    mo.md(f"Sandbox `{sandbox.sandbox_id}` stopped.")
    return


if __name__ == "__main__":
    app.run()
