# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "boto3==1.42.45",
#     "k8s==0.28.0",
#     "kubernetes==35.0.0",
#     "marimo>=0.20.2",
#     "mypy-boto3-s3>=1.42.37",
#     "ruamel-yaml>=0.19.1",
#     "typing-extensions>=4.15.0"
# ]
# ///

import marimo

from arena.notebooks.lib.coreweave import detect_cw_token
from arena.notebooks.lib.k8s import KubernetesConfigError
from arena.notebooks.lib.ui import security_disclaimer

__generated_with = "0.20.2"
app = marimo.App(width="medium", app_title="CoreWeave ARENA")

with app.setup:
    import json
    import time
    from collections.abc import Callable

    import marimo as mo
    from boto3.s3.transfer import TransferConfig
    from lib.auth_ui import (
        init_k8s,
        init_object_storage,
        process_k8s_form,
        process_storage_form,
    )
    from lib.coreweave import cw_token_input
    from lib.k8s import K8s
    from lib.storage.boto3 import run_s3_download_test, run_s3_upload_test
    from lib.storage.object_storage import MissingCredentialsError, ObjectStorage
    from lib.ui import about, banner, security_disclaimer, table_of_contents


@app.cell(hide_code=True)
def _():
    _elements = [
        banner(),
        about(
            "Boto3",
            """This notebook provides a walkthrough for benchmarking CoreWeave AI Object Storage (CAIOS) and LOTA using the Boto3 Python library.<br>
               _If you are running this notebook in edit mode, make sure you start by running all cells in the bottom right._
            """,
        ),
        table_of_contents(
            [
                {"title": "Bucket Operations", "description": "List and manage buckets"},
                {"title": "Boto3 Upload & Download Performance Tests", "description": "Local benchmarking"},
            ]
        ),
        security_disclaimer(),
    ]
    mo.vstack(_elements)
    return


@app.cell(hide_code=True)
def _():
    auto_k8s, kubeconfig_form, _ui = init_k8s()
    _ui
    return auto_k8s, kubeconfig_form


@app.cell(hide_code=True)
def _(auto_k8s: K8s, kubeconfig_form: mo.ui.form):
    k8s, _ui = process_k8s_form(auto_k8s, kubeconfig_form)
    _ui if _ui else None
    return (k8s,)


@app.cell(hide_code=True)
def _(k8s: K8s):
    auto_storage, cw_token_form, _ui = init_object_storage(k8s)
    _ui
    return auto_storage, cw_token_form


@app.cell(hide_code=True)
def _(auto_storage: ObjectStorage | None, cw_token_form: mo.ui.form, k8s: K8s):
    storage, _ui = process_storage_form(auto_storage, cw_token_form, k8s)
    _ui if _ui else None
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
def _(storage: ObjectStorage | None, k8s: K8s):
    mo.stop(storage is None)
    _initial_bucket_name = f"{k8s.org_id}-arena-bucket"
    create_bucket_form = (
        mo.md("""
        **Bucket Name:** {bucket_name}
        """)
        .batch(
            bucket_name=mo.ui.text(value=_initial_bucket_name, full_width=True)  # type: ignore
        )
        .form(submit_button_label="Create Bucket", clear_on_submit=False)
    )
    return (create_bucket_form,)


@app.cell(hide_code=True)
def _(create_bucket_form: mo.ui.form, storage: ObjectStorage | None):
    mo.stop(storage is None)

    _bucket_creation_result = None
    bucket_created = 0.0
    if create_bucket_form.value and create_bucket_form.value.get("bucket_name"):
        try:
            _name = create_bucket_form.value.get("bucket_name")
            storage.create_bucket(_name)
            bucket_created = time.time()  # timestamp so that multiple bucket creation cause re-run
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
def _(bucket_created: float, storage: ObjectStorage | None):
    if bucket_created:
        pass
    buckets = storage.list_buckets()
    _initial_bucket = buckets[0] if buckets else None

    bucket_dropdown = mo.ui.dropdown(options=buckets, value=_initial_bucket, label="**Bucket:**")
    use_lota_checkbox = mo.ui.checkbox(
        value=False, label="**Use LOTA** (For notebooks running inside GPU clusters only)"
    )

    _ui = mo.md(f"""
    ### Storage Endpoint Configuration
    /// admonition | About LOTA
        type: info

    [LOTA](https://docs.coreweave.com/products/storage/object-storage/lota/about#about-lota) provides faster access for GPU workloads by using a local cache but is only accessible from GPU clusters.
    If you're running locally or on a CPU-only cluster, keep this unchecked to use CAIOS.<br><br>
    {use_lota_checkbox}<br>
    {bucket_dropdown}<br>
    ///
    """)

    _ui
    return (bucket_dropdown, use_lota_checkbox)


@app.cell(hide_code=True)
def _(bucket_dropdown: mo.ui.dropdown, use_lota_checkbox: mo.ui.checkbox):
    bucket_name = bucket_dropdown.value
    use_lota = use_lota_checkbox.value
    return (bucket_name, use_lota)


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
            max_concurrency=mo.ui.number(start=1, stop=10000, value=300),  # type: ignore
        )
        .form(submit_button_label="Run Upload Test", clear_on_submit=False)
    )
    upload_form
    return (upload_form,)


@app.cell(hide_code=True)
def _(bucket_name: str, storage: ObjectStorage | None, upload_form: mo.ui.form, use_lota: bool):
    mo.stop(storage is None)

    upload_result = None
    if upload_form.value:
        with mo.status.spinner(
            title="Running Boto3 Upload Test",
            subtitle=f"Uploading to {bucket_name}",
        ):
            _form_values = upload_form.value.copy()
            _max_concurrency = _form_values.pop("max_concurrency")
            storage.update_max_pool_connections(_max_concurrency)
            storage.update_endpoint(use_lota=use_lota)

            _result = run_s3_upload_test(
                storage=storage,
                bucket_name=bucket_name,
                **_form_values,
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
def _(bucket_name: str, storage: ObjectStorage | None):
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
def _(object_key_dropdown: mo.ui.dropdown):
    if object_key_dropdown is not None:
        download_form = (
            mo.md("""
            ### Configure CoreWeave AI Object Storage Download Test
            - Object: {object_key}
            - Multipart Threshold (MB), use multipart for files greater than: {multipart_threshold_mb}
            - Chunk Size (MB), MB per part: {multipart_chunksize_mb}
            - Max Concurrency: {max_concurrency}
            """)
            .batch(
                object_key=object_key_dropdown,
                multipart_threshold_mb=mo.ui.number(start=1, stop=1000, value=50),  # type: ignore
                multipart_chunksize_mb=mo.ui.number(start=1, stop=1000, value=50),  # type: ignore
                max_concurrency=mo.ui.number(start=1, stop=10000, value=300),  # type: ignore
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
def _(bucket_name: str, download_form: mo.ui.form, storage: ObjectStorage | None, use_lota: bool):
    mo.stop(storage is None)

    download_result = None
    if download_form.value:
        with mo.status.spinner(
            title="Running Boto3 Download Test",
            subtitle=f"Downloading from {bucket_name}",
        ):
            _form_values = download_form.value.copy()
            _max_concurrency = _form_values.pop("max_concurrency")
            storage.update_max_pool_connections(_max_concurrency)
            storage.update_endpoint(use_lota=use_lota)

            _result = run_s3_download_test(
                storage=storage,
                bucket_name=bucket_name,
                **_form_values,
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


if __name__ == "__main__":
    app.run()
