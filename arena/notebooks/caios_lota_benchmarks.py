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
from typing import Callable

import marimo

__generated_with = "0.19.11"
app = marimo.App(width="medium", app_title="CoreWeave ARENA")

with app.setup:
    import json
    import os
    import time

    import marimo as mo
    from lib.k8s import K8s
    from lib.storage.object_storage import MissingCredentialsError, ObjectStorage
    from lib.storage.warp import get_warp_benchmark_results, run_warp_benchmark


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ![CoreWeave ARENA Banner](public/banner.jpg)
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # CoreWeave ARENA: Object Storage & LOTA

    /// admonition | About This Notebook
        type: info

    This notebook provides a walkthrough for benchmarking CoreWeave AI Object Storage (CAIOS) and LOTA.
    ///
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    /// details | Table of Contents

    - **Bucket Operations** - List and manage buckets
    - **Benchmarks** - Performance testing
    ///
    """)
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

    These credentials are used for S3 API access to CAIOS and LOTA.
    ///
    """)
    return


@app.cell(hide_code=True)
def _():
    use_lota_checkbox = mo.ui.checkbox(value=False, label="Use LOTA (GPU clusters only)")

    mo.md(f"""
    ### Storage Endpoint Configuration

    {use_lota_checkbox}

    /// admonition | About LOTA
        type: info

    [LOTA](https://docs.coreweave.com/products/storage/object-storage/lota/about#about-lota) provides faster access for GPU workloads by using a local cache but is only accessible from GPU clusters.
    If you're running locally or on CPU-only clusters, keep this unchecked to use CAIOS.
    ///
    """)

    return (use_lota_checkbox,)


@app.cell(hide_code=True)
def _(use_lota_checkbox):
    use_lota = use_lota_checkbox.value
    caios: ObjectStorage
    cw_token_required: bool = False
    try:
        caios = ObjectStorage.auto(use_lota=use_lota)
    except MissingCredentialsError:
        cw_token_required = True
    if cw_token_required:
        token_form = (
            mo.md("{cw_token}")
            .batch(cw_token=mo.ui.text(kind="password", placeholder="CW-SECRET-...", full_width=True))  # type: ignore
            .form(submit_button_label="Connect", bordered=False)
        )
        _ui = mo.md(
            f"""
            /// admonition | Manual Initialization Required
                type: warning

            Automatic credentials not found. Please enter your [CoreWeave access token](https://console.coreweave.com/tokens) to initialize the ObjectStorage client.
            ///

            {token_form}
            """
        )
    else:
        token_form = None
        _ui = mo.md("ObjectStorage client initialized successfully")

    _ui
    return caios, token_form, use_lota


@app.cell(hide_code=True)
def _(caios: ObjectStorage, form: mo.ui.form, region: str, use_lota: bool):
    storage: ObjectStorage
    if caios is not None:
        storage = caios
        status = "ObjectStorage client initialized with pod identity."
    elif form.value and form.value.get("cw_token"):
        storage = ObjectStorage.with_access_keys(use_lota=use_lota, region=region, cw_token=form.value["cw_token"])
        status = "ObjectStorage client initialized with provided token."
    else:
        status = "Please initialize the client above"
    mo.md(f"""
        /// admonition
        {status}
        """)
    return (storage,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ---
    ## Bucket Operations

    /// admonition | S3 Buckets
        type: info

    List and manage your S3 buckets. Buckets are the top-level containers for your objects.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(storage: ObjectStorage):
    get_buckets, set_buckets = mo.state(storage.list_buckets())
    buckets = get_buckets()

    _initial_bucket = buckets[0] if buckets else None
    bucket_dropdown = mo.ui.dropdown(options=buckets, value=_initial_bucket)
    create_bucket_form = (
        mo.md("""
        **Bucket Name:** {bucket_name}
        """)
        .batch(
            bucket_name=mo.ui.text(placeholder="my-bucket-name", full_width=True)  # type: ignore
        )
        .form(submit_button_label="Create Bucket", clear_on_submit=False)
    )
    bucket_refresh = mo.ui.button(label="Refresh Bucket List")

    return bucket_dropdown, create_bucket_form, buckets, set_buckets, bucket_refresh


@app.cell(hide_code=True)
def _(create_bucket_form: mo.ui.form, set_buckets, bucket_refresh: mo.ui.button, storage: ObjectStorage):
    _ui = None
    if create_bucket_form.value:
        try:
            _name = create_bucket_form.value.get("bucket_name")
            storage.create_bucket(_name)
            _ui = mo.md(
                f"Successfully created bucket {_name}. Please refresh the bucket list dropdown to see the new bucket."
            )
        except Exception as _e:
            _ui = mo.md(f"Failed to create bucket: {_e}")

    if bucket_refresh.value:
        set_buckets(storage.list_buckets())
        _ui = mo.md("Bucket list refreshed")
    _ui
    return


@app.cell(hide_code=True)
def _(create_bucket_form: mo.ui.form, buckets: list[str]):
    _ui = None
    if buckets:
        _ui = mo.md(f"""
        ### Create S3 Bucket

        {create_bucket_form}
        """)
    else:
        _ui = mo.md(f"""
        ### Create S3 Bucket

        /// admonition | No Buckets Found
            type: warning

        No buckets found in your account. Create one to get started:
        ///

        {create_bucket_form}
        """)
    _ui
    return


@app.cell(hide_code=True)
def _(bucket_dropdown: mo.ui.dropdown, buckets: list[str]):
    _ui = mo.md(f"""
        ### Select S3 Bucket for upload and download tests
        {bucket_dropdown}
        """)
    bucket_name = bucket_dropdown.value
    _ui


@app.cell(hide_code=True)
def _():
    upload_form = (
        mo.md("""
        ### Configure S3 Upload Test
        - Test File Size (GB): {test_file_size_gb}
        - Multipart Threshold (MB): {multipart_threshold_mb}
        - Chunk Size (MB): {multipart_chunksize_mb}
        - Max Concurrency: {max_concurrency}
        """)
        .batch(
            test_file_size_gb=mo.ui.number(start=0, stop=1000, step=10, value=10),  # type: ignore
            multipart_threshold_mb=mo.ui.number(start=1, stop=1000, value=50),  # type: ignore
            multipart_chunksize_mb=mo.ui.number(start=1, stop=1000, value=50),  # type: ignore
            max_concurrency=mo.ui.slider(1, 100, value=32, show_value=True),  # type: ignore
        )
        .form(submit_button_label="Run Upload Test", clear_on_submit=False)
    )
    upload_form
    return (upload_form,)


@app.cell(hide_code=True)
def _(bucket_name: str):
    def run_s3_upload_test(
        storage: ObjectStorage,
        bucket_name: str,
        test_file_size_gb: int = 1,
        multipart_threshold_mb: int = 8,
        multipart_chunksize_mb: int = 8,
        max_concurrency: int = 10,
    ):
        from boto3.s3.transfer import TransferConfig

        test_dir = "/tmp/bandwidth-test"
        test_filename = f"{test_file_size_gb}GB"
        os.makedirs(test_dir, exist_ok=True)
        file_size_bytes = int(test_file_size_gb * 1024 * 1024 * 1024)
        test_file = f"{test_dir}/{test_filename}"
        if not os.path.exists(test_file):
            print(f"Creating test file: {test_filename}...")
            chunk_size = 64 * 1024 * 1024  # 64 MB
            zero_chunk = b"\0" * chunk_size
            with open(test_file, "wb") as f:
                remaining = file_size_bytes
                while remaining > 0:
                    write_size = min(chunk_size, remaining)
                    f.write(zero_chunk[:write_size])
                    remaining -= write_size
                    progress = (file_size_bytes - remaining) / file_size_bytes * 100
                    print(f"Progress: {progress:.0f}%")
        else:
            print(f"Test file '{test_filename}' already exists locally, proceeding to upload.")

        transfer_config = TransferConfig(
            multipart_threshold=multipart_threshold_mb * 1024 * 1024,
            multipart_chunksize=multipart_chunksize_mb * 1024 * 1024,
            max_concurrency=max_concurrency,
            use_threads=True,
        )
        file_key = f"benchmark/{test_file_size_gb}GB"

        print(f"""
        --- S3 Upload Test (Boto3) ---
        Bucket: s3://{bucket_name}
        Key: {file_key}
        Multipart Threshold: {multipart_threshold_mb} MB
        Chunk Size: {multipart_chunksize_mb} MB
        Max Concurrency: {max_concurrency}
        --- S3 Upload Test (Boto3) ---
        """)

        start = time.time()
        try:
            storage.s3_client.upload_file(test_file, bucket_name, file_key, Config=transfer_config)
            elapsed = time.time() - start

            size_bytes = os.path.getsize(test_file)
            size_gb = size_bytes / (1024 * 1024 * 1024)
            size_mb = size_bytes / (1024 * 1024)
            bandwidth_mbs = size_mb / elapsed
            bandwidth_gbps = (size_bytes * 8) / elapsed / 1_000_000_000

            print(f"""
        --- S3 Upload Stats ---
        Size: {size_gb:.2f} GB
        Time: {elapsed:.2f} seconds
        Bandwidth: {bandwidth_mbs:.2f} MB/s ({bandwidth_gbps:.2f} Gbps)
        --- S3 Upload Stats ---
        """)
        except Exception as e:
            print(f"Upload failed: {e}")
        return file_key

    return (run_s3_upload_test,)


@app.cell(hide_code=True)
def _(run_s3_upload_test: Callable, bucket_name: str, storage: ObjectStorage, upload_form: mo.ui.form):
    if upload_form.value:
        with mo.status.spinner(
            title="Running Upload Test",
            subtitle=f"Uploading to {bucket_name}",
        ):
            run_s3_upload_test(
                storage=storage,
                bucket_name=bucket_name,
                **upload_form.value,
            )
    return


@app.cell(hide_code=True)
def _(storage: ObjectStorage, bucket_name: str):
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
    return object_key_dropdown, object_keys


@app.cell(hide_code=True)
def _(bucket_dropdown: mo.ui.dropdown, object_key_dropdown: mo.ui.dropdown):
    if object_key_dropdown is not None:
        download_form = (
            mo.md("""
            ### Configure S3 Download Test
            - Object: {object_key}
            - Multipart Threshold (MB): {multipart_threshold_mb}
            - Chunk Size (MB): {multipart_chunksize_mb}
            - Max Concurrency: {max_concurrency}
            """)
            .batch(
                object_key=object_key_dropdown,  # type: ignore
                multipart_threshold_mb=mo.ui.number(start=1, stop=1000, value=50),  # type: ignore
                multipart_chunksize_mb=mo.ui.number(start=1, stop=1000, value=50),  # type: ignore
                max_concurrency=mo.ui.slider(1, 100, value=32, show_value=True),  # type: ignore
            )
            .form(submit_button_label="Run Download Test", clear_on_submit=False)
        )
        _ui = download_form
    else:
        download_form = None
        _ui = mo.md("""
        /// admonition | No Objects Available
            type: warning

        No objects available for download. Please select a bucket and upload a file first using the upload test above.
        ///
        """)

    _ui
    return (download_form,)


@app.cell(hide_code=True)
def _():
    def run_s3_download_test(
        storage: ObjectStorage,
        bucket_name: str,
        object_key: str,
        multipart_threshold_mb: int = 8,
        multipart_chunksize_mb: int = 8,
        max_concurrency: int = 10,
    ):
        from boto3.s3.transfer import TransferConfig

        if not bucket_name or not object_key:
            print("bucket_name and object_key are required")
            return

        test_dir = "/tmp/bandwidth-test"
        os.makedirs(test_dir, exist_ok=True)

        # Extract filename from object_key for local storage
        filename = os.path.basename(object_key)
        output_path = f"{test_dir}/{filename}"

        transfer_config = TransferConfig(
            multipart_threshold=multipart_threshold_mb * 1024 * 1024,
            multipart_chunksize=multipart_chunksize_mb * 1024 * 1024,
            max_concurrency=max_concurrency,
            use_threads=True,
        )

        print(f"""
        --- S3 Download Test (Boto3) ---
        Bucket: s3://{bucket_name}
        Key: {object_key}
        Multipart Threshold: {multipart_threshold_mb} MB
        Chunk Size: {multipart_chunksize_mb} MB
        Max Concurrency: {max_concurrency}
        --- S3 Download Test (Boto3) ---
        """)

        start = time.time()
        try:
            storage.s3_client.download_file(bucket_name, object_key, output_path, Config=transfer_config)
            elapsed = time.time() - start

            size_bytes = os.path.getsize(output_path)
            size_gb = size_bytes / (1024 * 1024 * 1024)
            size_mb = size_bytes / (1024 * 1024)
            bandwidth_mbs = size_mb / elapsed
            bandwidth_gbps = (size_bytes * 8) / elapsed / 1_000_000_000

            print(f"""
        --- S3 Download Stats ---
        Size: {size_gb:.2f} GB
        Time: {elapsed:.2f} seconds
        Bandwidth: {bandwidth_mbs:.2f} MB/s ({bandwidth_gbps:.2f} Gbps)
        --- S3 Download Stats ---
        """)
        except Exception as e:
            print(f"Download failed: {e}")

    return (run_s3_download_test,)


@app.cell(hide_code=True)
def _(bucket_name: str, download_form: mo.ui.form, run_s3_download_test: Callable, storage: ObjectStorage):
    if download_form.value:
        with mo.status.spinner(
            title="Running Download Test",
            subtitle=f"Downloading from {bucket_name}",
        ):
            run_s3_download_test(
                storage=storage,
                bucket_name=bucket_name,
                **download_form.value,
            )
    return


@app.cell(hide_code=True)
def _(bucket_name: str, storage: ObjectStorage):
    warp_form = (
        mo.md("""
            ### Configure Warp Benchmark
            - {operation}
            """)
        .batch(
            operation=mo.ui.dropdown(options=["get", "put", "delete", "list", "stat"], value="get", label="Operation:"),
        )
        .form(submit_button_label="Run Warp Benchmark", clear_on_submit=False)
    )

    description = mo.md(r"""
    ---
    ## Warp Benchmark

    /// admonition | About Warp
        type: info

    [Warp](https://github.com/minio/warp) is a benchmarking tool for S3-compatible object storage that runs comprehensive performance tests on GET, PUT, DELETE, LIST, and STAT operations.
    ///
    """)

    mo.vstack([description, warp_form])
    return (warp_form,)


@app.cell(hide_code=True)
def _(warp_form: mo.ui.form, storage: ObjectStorage, bucket_name: str):
    if warp_form.value:
        warp_config = warp_form.value
        warp_operation = warp_config.get("operation", "get")

        k8s = K8s()
        with mo.status.spinner(
            title="Running Warp Benchmark",
            subtitle=f"Benchmarking bucket: {bucket_name}",
        ):
            warp_submit_results = run_warp_benchmark(k8s, storage, bucket_name)

        result_section = mo.md(f"""
/// admonition | Benchmark Started

Warp benchmark job submitted successfully.

**Operation:** {warp_operation}

Submit Results:
```json
{json.dumps(warp_submit_results, indent=2)}

```
Results will be viewable below shortly or in the pod logs in-cluster.
///
        """)
        mo.output.replace(result_section)


@app.cell(hide_code=True)
def _(k8s: K8s, warp_submit_results: dict[str : list[str]], warp_form: mo.ui.form):
    if warp_form.value:
        warp_job_name = warp_submit_results["created"][0].split("/")[1]
        namespace = os.getenv("POD_NAMESPACE", "tenant-slurm")

        _timeout_seconds = 600
        _start_time = time.time()
        _log_lines = []

        with mo.status.spinner(title="Waiting for Warp benchmark to complete") as _spinner:
            while time.time() - _start_time < _timeout_seconds:
                warp_results = get_warp_benchmark_results(k8s, warp_job_name, namespace)
                _status = warp_results.get("status", "unknown")
                _elapsed = int(time.time() - _start_time)

                _spinner.update(subtitle=f"{_status} - {_elapsed}s")

                _current_logs = warp_results.get("logs", [])
                if len(_current_logs) > len(_log_lines):
                    _log_lines = _current_logs
                    _recent_logs = "\n".join(_log_lines[-30:])
                    mo.output.replace(
                        mo.vstack(
                            [
                                mo.md(f"**Status:** {_status} | **Elapsed:** {_elapsed}s"),
                                mo.md(f"```\n{_recent_logs}\n```"),
                            ]
                        )
                    )

                if _status in ["succeeded", "failed", "completed"]:
                    break
                time.sleep(5)

        _full_logs = "\n".join(_log_lines)
        _final_output = mo.md(f"""
### Benchmark Complete

**Status:** {_status}
```\n{_full_logs}\n```
""")
        mo.output.replace(_final_output)
    return (warp_results,)


if __name__ == "__main__":
    app.run()
