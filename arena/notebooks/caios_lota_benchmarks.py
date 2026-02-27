# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "boto3==1.42.45",
#     "k8s==0.28.0",
#     "kubernetes==35.0.0",
#     "marimo>=0.19.7",
#     "marimo[lsp]>=0.19.7",
#     "mypy-boto3-s3>=1.42.37",
#     "shell==1.0.1",
#     "ruamel-yaml>=0.19.1"
# ]
# ///

import marimo

__generated_with = "0.20.2"
app = marimo.App(width="medium", app_title="CoreWeave ARENA")

with app.setup:
    import json
    import os
    import time
    from collections.abc import Callable

    import marimo as mo
    from boto3.s3.transfer import TransferConfig
    from lib.k8s import K8s
    from lib.reusable_cells import about, banner, cw_token_input, table_of_contents
    from lib.storage.boto3 import run_s3_download_test, run_s3_upload_test
    from lib.storage.object_storage import MissingCredentialsError, ObjectStorage
    from lib.storage.warp import WarpRunner


@app.cell(hide_code=True)
def _():
    _elements = [
        banner(),
        about(
            "Object Storage & LOTA",
            """This notebook provides a walkthrough for benchmarking CoreWeave AI Object Storage (CAIOS) and LOTA.<br>
               _If you are running this notebook in edit mode, make sure you start by running all cells in the bottom right._
            """,
        ),
        table_of_contents(
            [
                {"title": "Bucket Operations", "description": "List and manage buckets"},
                {"title": "Boto3 Upload & Download Performance Tests", "description": "Local benchmarking"},
                {"title": "Warp Benchmark", "description": "Multinode cluster benchmarking"},
            ]
        ),
    ]
    mo.vstack(_elements)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ---
    ## Access Keys

    /// attention | Console Setup Required
    Access keys are typically set up for you in the notebook automatically.

    If you'd like to use object storage outside of this notebook you'll need to create your own Access Key and Secret Access Key in the [CoreWeave Console](https://console.coreweave.com/object-storage/access-keys)
    See [here](https://docs.coreweave.com/docs/products/storage/object-storage/get-started-caios) for more details.

    These credentials are used for API access to CAIOS and LOTA.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(use_lota_checkbox):
    _ui = None
    k8s = K8s()
    use_lota = use_lota_checkbox.value
    caios: ObjectStorage | None = None
    cw_token_required: bool = False
    try:
        caios = ObjectStorage.auto(k8s, use_lota=use_lota)
    except MissingCredentialsError:
        cw_token_required = True

    _ui, token_form = cw_token_input(token_required=cw_token_required)
    _ui
    return caios, k8s, token_form, use_lota


@app.cell(hide_code=True)
def _(caios: ObjectStorage | None, k8s, token_form, use_lota):
    storage: ObjectStorage | None = None
    if caios is not None:
        storage = caios
        status = "ObjectStorage client initialized with pod identity."
    elif token_form.value and token_form.value.get("cw_token"):
        storage = ObjectStorage.with_access_keys(k8s=k8s, use_lota=use_lota, cw_token=token_form.value["cw_token"])
    return (storage,)


@app.cell(hide_code=True)
def _(storage: ObjectStorage | None):
    # Stop execution of downstream cells if storage is not initialized properly
    mo.stop(
        storage is None,
        mo.md("""
        /// admonition | Waiting for Initialization
            type: warning

        Please complete the initialization above before proceeding.
        ///
    """),
    )
    mo.md("""
        /// admonition | Storage Client Initialized
            type: success

        Successfully initialized ObjectStorage client. You can now manage buckets and run benchmarks.
    """)
    return


@app.cell(hide_code=True)
def _():
    use_lota_checkbox = mo.ui.checkbox(value=False, label="Use LOTA (For notebooks running inside GPU clusters only)")

    mo.md(f"""
    ### Storage Endpoint Configuration
    /// admonition | About LOTA
        type: info

    [LOTA](https://docs.coreweave.com/products/storage/object-storage/lota/about#about-lota) provides faster access for GPU workloads by using a local cache but is only accessible from GPU clusters.
    If you're running locally or on CPU-only clusters, keep this unchecked to use CAIOS.
    ///

    {use_lota_checkbox}
    """)
    return (use_lota_checkbox,)


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
def _(storage: ObjectStorage | None):
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
def _(bucket_created, storage: ObjectStorage | None):
    if bucket_created:
        pass
    buckets = storage.list_buckets()
    _initial_bucket = buckets[0] if buckets else None
    bucket_dropdown = mo.ui.dropdown(options=buckets, value=_initial_bucket)
    return (bucket_dropdown,)


@app.cell(hide_code=True)
def _(create_bucket_form, storage: ObjectStorage | None):
    mo.stop(storage is None)

    _bucket_creation_result = None
    bucket_created = 0.0
    if create_bucket_form.value:
        try:
            _name = create_bucket_form.value.get("bucket_name")
            storage.create_bucket(_name)
            bucket_created = time.time()  # timestamp so that multiple bucket creation cause re-run
            _bucket_creation_result = mo.callout(mo.md(f"Successfully created bucket **{_name}**"), kind="success")
        except Exception as _e:
            _bucket_creation_result = mo.callout(mo.md(f"Failed to create bucket: {_e}"), kind="danger")

    _ui = mo.md(f"""
    ### Create S3 Bucket
    {create_bucket_form}
    """)

    _output = mo.vstack([_ui, _bucket_creation_result] if _bucket_creation_result else [_ui])
    _output
    return (bucket_created,)


@app.cell(hide_code=True)
def _(bucket_dropdown):
    _ui = mo.md(f"""
        ### Select CoreWeave AI Object Storage Bucket for upload and download tests
        {bucket_dropdown}
        """)
    bucket_name = bucket_dropdown.value
    _ui
    return (bucket_name,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Boto3 Upload & Download Performance Tests

    /// admonition | About Boto3 Tests
        type: info

    These upload and download tests measure the network bandwidth between the _machine running this notebook_ and CoreWeave AI Object Storage using the Boto3 Python library.

    - **Upload Test**: Measures how fast you can write data from this machine to object storage
    - **Download Test**: Measures how fast you can read data from object storage to this machine

    Performance depends on:
    - Your current network connection quality
    - The geographical distance to the storage endpoint
    - Whether you're using LOTA (GPU cluster) or CAIOS (standard endpoint)

    **Note**: Results will vary based on where this notebook is running (local laptop vs. CoreWeave GPU cluster).
    ///
    """)
    return


@app.cell(hide_code=True)
def _(storage: ObjectStorage | None):
    mo.stop(storage is None)

    upload_form = (
        mo.md("""
        ### Configure CoreWeave AI Object Storage Upload Test
        - Test File Size (GB): {test_file_size_gb}
        - Multipart Threshold (MB): {multipart_threshold_mb}
        - Chunk Size (MB): {multipart_chunksize_mb}
        - Max Concurrency: {max_concurrency}
        """)
        .batch(
            test_file_size_gb=mo.ui.number(start=0, stop=1000, value=10),  # type: ignore
            multipart_threshold_mb=mo.ui.number(start=1, stop=1000, value=50),  # type: ignore
            multipart_chunksize_mb=mo.ui.number(start=1, stop=1000, value=50),  # type: ignore
            max_concurrency=mo.ui.slider(1, 1000, value=300, show_value=True),  # type: ignore
        )
        .form(submit_button_label="Run Upload Test", clear_on_submit=False)
    )
    upload_form
    return (upload_form,)


@app.cell(hide_code=True)
def _(bucket_name, storage: ObjectStorage | None, upload_form):
    mo.stop(storage is None)

    upload_result = None
    if upload_form.value:
        with mo.status.spinner(
            title="Running Boto3 Upload Test",
            subtitle=f"Uploading to {bucket_name}",
        ):
            _result = run_s3_upload_test(
                storage=storage,
                bucket_name=bucket_name,
                **upload_form.value,
            )
            if _result["success"]:
                upload_result = mo.callout(
                    mo.md(f"""
                    ### Boto3 Upload Complete
                    - **File**: `{_result["file_key"]}`
                    - **Size**: {_result["size_gb"]:.2f} GB
                    - **Time**: {_result["elapsed"]:.2f} seconds
                    - **Bandwidth**: {_result["bandwidth_mbs"]:.2f} MB/s ({_result["bandwidth_gbps"]:.2f} Gbps)
                    """),
                    kind="success",
                )
            else:
                upload_result = mo.callout(mo.md(f"Upload failed: {_result['error']}"), kind="danger")
    upload_result
    return


@app.cell(hide_code=True)
def _(bucket_name, storage: ObjectStorage | None):
    mo.stop(storage is None)

    if bucket_name:
        objects_result = storage.list_objects(bucket_name, prefix="benchmark/")
        object_keys = [obj["Key"] for obj in objects_result["objects"]]

        if object_keys:
            object_key_dropdown = mo.ui.dropdown(options=object_keys, value=object_keys[0] if object_keys else "")
        else:
            object_key_dropdown = None
            object_keys = []
    else:
        object_key_dropdown = None
        object_keys = []
    return (object_key_dropdown,)


@app.cell(hide_code=True)
def _(object_key_dropdown):
    if object_key_dropdown is not None:
        download_form = (
            mo.md("""
            ### Configure CoreWeave AI Object Storage Download Test
            - Object: {object_key}
            - Multipart Threshold (MB): {multipart_threshold_mb}
            - Chunk Size (MB): {multipart_chunksize_mb}
            - Max Concurrency: {max_concurrency}
            """)
            .batch(
                object_key=object_key_dropdown,
                multipart_threshold_mb=mo.ui.number(start=1, stop=1000, value=50),  # type: ignore
                multipart_chunksize_mb=mo.ui.number(start=1, stop=1000, value=50),  # type: ignore
                max_concurrency=mo.ui.slider(1, 1000, value=300, show_value=True),  # type: ignore
            )
            .form(submit_button_label="Run Download Test", clear_on_submit=False)
        )
        _ui = download_form
    else:
        download_form = mo.md("").batch().form()
        _ui = mo.md("""
        /// admonition | CoreWeave AI Object Storage Download Test
            type: warning

        No objects available for download. Please select a bucket and upload a file first using the upload test above.
        ///
        """)

    _ui
    return (download_form,)


@app.cell(hide_code=True)
def _(bucket_name, download_form, storage: ObjectStorage | None):
    mo.stop(storage is None)

    download_result = None
    if download_form.value:
        with mo.status.spinner(
            title="Running Boto3 Download Test",
            subtitle=f"Downloading from {bucket_name}",
        ):
            _result = run_s3_download_test(
                storage=storage,
                bucket_name=bucket_name,
                **download_form.value,
            )
            if _result["success"]:
                download_result = mo.callout(
                    mo.md(f"""
                    ### Boto3 Download Complete
                    - **Object**: `{_result["object_key"]}`
                    - **Output**: `{_result["output_path"]}`
                    - **Size**: {_result["size_gb"]:.2f} GB
                    - **Time**: {_result["elapsed"]:.2f} seconds
                    - **Bandwidth**: {_result["bandwidth_mbs"]:.2f} MB/s ({_result["bandwidth_gbps"]:.2f} Gbps)
                    """),
                    kind="success",
                )
            else:
                download_result = mo.callout(mo.md(f"Download failed: {_result['error']}"), kind="danger")

    download_result
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
    mo.stop(storage is None)

    _node_count = 1
    # get the node count to set default concurrency, rec from storage is 300/node
    _gpu_nodes = k8s.get_nodes().get("gpu", {})
    _gpu_count = sum(node.get("node_count", 0) for node in _gpu_nodes.values())
    if not _gpu_count:
        _cpu_nodes = k8s.get_nodes().get("cpu", {})
        _node_count = sum(node.get("node_count", 0) for node in _cpu_nodes.values())
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
