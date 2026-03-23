# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "k8s==0.28.0",
#     "kubernetes==35.0.0",
#     "marimo>=0.20.2",
#     "mypy-boto3-s3>=1.42.37",
#     "ruamel-yaml>=0.19.1",
#     "typing-extensions>=4.15.0"
# ]
# ///

# All dependencies for your notebook and any libraries used by it MUST be listed above.
# If you don't know the version, you can find it by `uv add {package-name}` then checking in pyproject.toml

import marimo

__generated_with = "0.20.2"
app = marimo.App(width="medium", app_title="CoreWeave ARENA")

# All imports needed by your notebook go below.
# The example below paths will need to be updated to the correct relative path
with app.setup:
    import marimo as mo

    from ..notebooks.lib.auth_ui import (
        init_k8s,
        init_object_storage,
        process_k8s_form,
        process_storage_form,
    )
    from ..notebooks.lib.k8s import K8s
    from ..notebooks.lib.storage.object_storage import ObjectStorage
    from ..notebooks.lib.tests.boto3 import run_s3_upload_test
    from ..notebooks.lib.ui import about, banner, security_disclaimer, table_of_contents


# This should be in every notebook to have a standard style for the header
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


# The following two cells result in having a reusable `k8s` object you can use to interact with the cluster.
# If the auth can't be found automatically, a kubeconfig path input cell will appear and allow for manual specification
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


# The following two cells result in having a reusable `storage` object you can use to interact with the object storage.
# If the auth can't be found automatically, a cw_token input cell will appear and allow for manual specification.
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


# Below is an example of how to create a UI form with multiple variables you can use to run a separate function
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


# Then you submit a run and show the results in a separate cell like below
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
