# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "boto3==1.42.45",
#     "k8s==0.28.0",
#     "kubernetes==35.0.0",
#     "marimo>=0.19.7",
#     "mypy-boto3-s3>=1.42.37",
#     "ruamel-yaml>=0.19.1"
# ]
# ///

import marimo

__generated_with = "0.20.2"
app = marimo.App(width="medium", app_title="CoreWeave ARENA")

with app.setup:
    import json
    import time

    import marimo as mo
    from lib.auth_ui import (
        init_k8s,
        init_object_storage,
        process_k8s_form,
        process_storage_form,
    )
    from lib.k8s import K8s
    from lib.storage.object_storage import ObjectStorage
    from lib.storage.warp import WarpRunner
    from lib.ui import about, banner, table_of_contents


@app.cell(hide_code=True)
def _():
    _elements = [
        banner(),
        about(
            "Warp",
            """This notebook provides a walkthrough for benchmarking CoreWeave AI Object Storage (CAIOS) and LOTA inside a CoreWeave cluster using the Minio Warp tool.<br>
               _If you are running this notebook in edit mode, make sure you start by running all cells in the bottom right._
            """,
        ),
        table_of_contents(
            [
                {"title": "Bucket Operations", "description": "List and manage buckets"},
                {"title": "Warp Benchmark", "description": "Multinode cluster benchmarking"},
            ]
        ),
    ]
    mo.vstack(_elements)
    return


@app.cell(hide_code=True)
def _():
    auto_k8s, kubeconfig_form, _ui = init_k8s()
    _ui
    return auto_k8s, kubeconfig_form


@app.cell(hide_code=True)
def _(auto_k8s, kubeconfig_form):
    k8s, _msgs = process_k8s_form(auto_k8s, kubeconfig_form)
    mo.output.append(mo.vstack(_msgs)) if _msgs else None
    return (k8s,)


@app.cell(hide_code=True)
def _(k8s):
    auto_storage, cw_token_form, _ui = init_object_storage(k8s)
    _ui
    return auto_storage, cw_token_form


@app.cell(hide_code=True)
def _(auto_storage, cw_token_form, k8s):
    storage, _msgs = process_storage_form(auto_storage, cw_token_form, k8s)
    mo.output.append(mo.vstack(_msgs)) if _msgs else None
    return (storage,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ---
    ## Bucket Operations

    /// admonition | CoreWeave AI Object Storage Buckets
        type: info

    List and manage your CoreWeave AI Object Storage buckets. Buckets are the top-level containers for your objects.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(storage):
    mo.stop(storage is None)

    create_bucket_form = (
        mo.md("""
        **Bucket Name:** {bucket_name}
        """)
        .batch(
            bucket_name=mo.ui.text(placeholder="my-bucket-name", full_width=True)  # type: ignore
        )
        .form(submit_button_label="Create Bucket", clear_on_submit=False)
    )
    return (create_bucket_form,)


@app.cell(hide_code=True)
def _(create_bucket_form, storage: ObjectStorage):
    mo.stop(storage is None)

    _bucket_creation_result = None
    bucket_created = 0.0
    if create_bucket_form.value:
        try:
            _name = create_bucket_form.value.get("bucket_name")
            storage.create_bucket(_name)
            bucket_created = time.time()  # timestamp so that multiple bucket creation cause re-run of dropdown
            _bucket_creation_result = mo.callout(mo.md(f"Successfully created bucket **{_name}**"), kind="success")
        except Exception as _e:
            _bucket_creation_result = mo.callout(mo.md(f"Failed to create bucket: {_e}"), kind="danger")

    _ui = mo.md(f"""
    ### Create CoreWeave AI Object Storage Bucket
    {create_bucket_form}
    """)

    _output = mo.vstack([_ui, _bucket_creation_result] if _bucket_creation_result else [_ui])
    _output
    return (bucket_created,)


@app.cell(hide_code=True)
def _(bucket_created, storage):
    if bucket_created:
        pass
    buckets = storage.list_buckets()
    _initial_bucket = buckets[0] if buckets else None
    bucket_dropdown = mo.ui.dropdown(options=buckets, value=_initial_bucket)
    return (bucket_dropdown,)


@app.cell(hide_code=True)
def _(bucket_dropdown):
    _ui = mo.md(f"""
        ### Select CoreWeave AI Object Storage Bucket for upload and download tests
        {bucket_dropdown}
        """)
    bucket_name = bucket_dropdown.value
    _ui
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ---
    ## Warp Benchmark

    /// admonition | About Warp Tests
        type: info
    [Warp](https://github.com/minio/warp) is a benchmarking tool for S3-compatible object storage that runs comprehensive performance tests on GET, PUT, DELETE, LIST, and STAT operations.

    Results represent the **actual performance your CKS workloads** (pods, jobs, deployments, sunk) can expect when accessing CoreWeave AI Object Storage.

    Performance depends on:
    - LOTA endpoint: High-speed locally cached access for GPU clusters
    - CAIOS endpoint: Standard network access
    - Object size, concurrency level, and operation type
    ///
    """)
    return


@app.cell(hide_code=True)
def _(bucket_name, k8s, storage: ObjectStorage | None):
    mo.stop(storage is None or k8s is None)

    _node_count = 1
    # get the node count to set default concurrency, rec from storage is 300/node
    _gpu_count = k8s.gpu_node_count
    if not _gpu_count:
        _cpu_nodes = k8s.cpu_node_count
        _node_count = k8s.cpu_node_count
    else:
        _node_count = _gpu_count - 1  # subtract 1 for the warp server node
    _default_concurrency = _node_count * 300

    warp_runner = WarpRunner(
        k8s,
        bucket_name,
        storage,
    )
    warp_form = (
        mo.md(f"""
            ### Configure Warp Benchmark for cluster **"{k8s.cluster_name}"** in the **"{warp_runner.namespace}"** namespace.
            If you want to benchmark a different cluster, set the _KUBECONFIG_ env var and context to the desired cluster.<br>
            If you'd like the benchmark pods in a different namespace set the _POD_NAMESPACE_ env var.
            - {{operation}}
            - {{duration}}
            - {{objects}}
            - {{concurrency}}
            """)
        .batch(
            operation=mo.ui.dropdown(  # type: ignore
                options=["get", "put", "delete", "list", "stat", "mixed"],
                value="get",
                label="Operation:",
            ),
            duration=mo.ui.number(1, 60, step=1, value=10, label="Duration (min):"),  # type: ignore
            objects=mo.ui.number(1000, 1_000_000, step=1, value=1000, label="Objects:"),  # type: ignore
            concurrency=mo.ui.number(1, 1000, step=1, value=_default_concurrency, label="Concurrency:"),  # type: ignore
        )
        .form(submit_button_label="Run Warp Benchmark", clear_on_submit=False)
    )

    warp_form
    return warp_form, warp_runner


@app.cell(hide_code=True)
def _(bucket_name, storage: ObjectStorage | None, warp_form, warp_runner):
    mo.stop(storage is None)

    if warp_form.value:
        warp_config = warp_form.value
        warp_duration = warp_config.get("duration", 10)
        warp_operation = warp_config.get("operation", "get")
        warp_objects = warp_config.get("objects", "1000")
        warp_concurrency = warp_config.get("concurrency", 300)

        with mo.status.spinner(
            title="Running Warp Benchmark",
            subtitle=f"Benchmarking bucket: {bucket_name}",
        ):
            warp_submit_results = warp_runner.run_benchmark(
                warp_operation,
                warp_duration,
                warp_objects,
                warp_concurrency,
            )

        result_section = mo.md(f"""
    /// admonition | Benchmark Started

    Warp benchmark job submitted successfully.

    **Operation:** {warp_operation}
    **Endpoint:** {storage.endpoint_url}
    **Objects:** {warp_objects}
    **Duration:** {warp_duration}m

    Submit Results:
    ```json
    {json.dumps(warp_submit_results, indent=2)}

    ```
    Results will be viewable below shortly or in the pod logs in-cluster.<br>
    Also, review the Grafana dashboards:<br>
    - [CAIOS Usage](https://cks-grafana.coreweave.com/d/bebi5t788t6v4c/caios-usage)
    - [CAIOS Lota](https://cks-grafana.coreweave.com/d/eeff523hiaewwc/caios-lota)
    ///
        """)
        mo.output.replace(result_section)
    return (warp_operation,)


@app.cell(hide_code=True)
def _(storage: ObjectStorage | None, warp_form, warp_operation, warp_runner):
    mo.stop(storage is None)

    if warp_form.value:
        _start_time = time.time()
        _log_text = ""
        _recent_logs = ""
        _status = ""

        with mo.status.spinner(title="Running Warp Benchmark") as _spinner:
            while _status not in ["succeeded", "failed", "completed"]:
                warp_results = warp_runner.get_results()
                _status = warp_results.get("status", "unknown")

                _current_logs = warp_results.get("logs", [])
                if len(_current_logs) > len(_log_text):
                    _log_text = _current_logs
                    _log_lines = _log_text.split("\n") if _log_text else []
                    _recent_logs = "\n".join(_log_lines[-30:])

                mo.output.replace(
                    mo.vstack(
                        [
                            mo.md(f"""
    ### Warp Benchmark Progress

    **Status:** {_status}
    **Operation:** {warp_operation}
    **Endpoint:** {storage.endpoint_url}
                            """),
                            mo.md(f"#### Recent Logs (last 30 lines)\n```\n{_recent_logs}\n```"),
                        ]
                    )
                )
                time.sleep(5)

        _total_time = int(time.time() - _start_time)

        _final_output = mo.md(f"""
    ### Benchmark Complete

    **Total Time:** {_total_time}s
    **Operation:** {warp_operation}
    **Endpoint:** {storage.endpoint_url}
    **Status:** {_status}
    ```\n{_log_text}\n```
    """)
        mo.output.replace(_final_output)
    return


if __name__ == "__main__":
    app.run()
