# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "boto3==1.42.45",
#     "k8s==0.28.0",
#     "kubernetes==35.0.0",
#     "marimo>=0.19.7",
#     "marimo[lsp]>=0.19.7",
#     "mypy-boto3-s3>=1.42.37",
#     "shell==1.0.1"
# ]
# ///

import marimo

__generated_with = "0.19.11"
app = marimo.App(width="medium", app_title="CoreWeave ARENA")

with app.setup:
    import json
    import os
    import time

    import marimo as mo
    from arena.object_storage_helpers import MissingCredentialsError, ObjectStorage


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ![CoreWeave ARENA Banner](public/banner.jpg)
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # CoreWeave AI Labs: Object Storage & LOTA

    /// admonition | About This Notebook
        type: info

    This notebook provides a walkthrough for setting up and benchmarking CoreWeave AI Object Storage (CAIOS) and LOTA.
    ///
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    /// details | Table of Contents

    - **Access Keys** - Create credentials in the console
    - **Organizational Policies** - Set S3 access policies
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
    caios: ObjectStorage
    cw_token_required: bool = False
    try:
        caios = ObjectStorage.auto(use_lota=False)
    except MissingCredentialsError:
        cw_token_required = True
    if cw_token_required:
        form = (
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

            {form}
            """
        )
    else:
        form = None
        _ui = mo.md("ObjectStorage client initialized successfully")

    _ui
    return caios, form


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
    ## 3. Bucket Operations

    /// admonition | S3 Buckets
        type: info

    List and manage your S3 buckets. Buckets are the top-level containers for your objects.
    ///
    """)
    return


# @app.cell(hide_code=True)
# def _(storage: ObjectStorage):
#     buckets = storage.list_buckets()

#     if buckets:
#         bucket_dropdown = mo.ui.dropdown(options=buckets, label="Select Bucket")
#         bucket_widget = bucket_dropdown
# else:
#     bucket_dropdown = None
#     create_bucket_form = (
#         mo.md("""
#         **Bucket Name:** {bucket_name}
#         """)
#         .batch(
#             bucket_name=mo.ui.text(placeholder="my-bucket-name", full_width=True)  # type: ignore
#         )
#         .form(submit_button_label="Create Bucket", clear_on_submit=False)
#     )
#     bucket_widget = create_bucket_form

# return bucket_dropdown, bucket_widget, buckets


# @app.cell(hide_code=True)
# def _(bucket_widget, buckets):
#     if buckets:
#         mo.md(f"""
#         ### Select S3 Bucket

#         Choose a bucket for upload and download tests:

#         {bucket_widget}
#         """)
#     else:
#         mo.md(f"""
#         ### Create S3 Bucket

#         /// admonition | No Buckets Found
#             type: warning

#         No buckets found in your account. Create one to get started:
#         ///

#         {bucket_widget}
#         """)
#     return


# # @app.cell(hide_code=True)
# # def _(bucket_widget, storage: ObjectStorage):
# #     if hasattr(bucket_widget, "value") and bucket_widget.value and "bucket_name" in bucket_widget.value:
# #         new_bucket_name = bucket_widget.value["bucket_name"]
# #         if new_bucket_name:
# #             try:
# #                 success = storage.create_bucket(new_bucket_name)
# #                 if success:
# #                     mo.md(f"""
# #                     /// admonition | Bucket Created
# #                         type: success

# #                     Successfully created bucket: `{new_bucket_name}`

# #                     Please refresh or re-run the cells to see the new bucket.
# #                     ///
# #                     """)
# #                 else:
# #                     mo.md(f"""
# #                     /// admonition | Creation Failed
# #                         type: error

# #                     Failed to create bucket: `{new_bucket_name}`
# #                     ///
# #                     """)
# #             except Exception as e:
# #                 mo.md(f"""
# #                 /// admonition | Error
# #                     type: error

# #                 Error creating bucket: {str(e)}
# #                 ///
# #                 """)
# #     return


# @app.cell(hide_code=True)
# def _(bucket_dropdown):
#     upload_form = (
#         mo.md("""
#         ### Configure S3 Upload Test
#         - Bucket: {bucket_name}
#         - Test File Size (GB): {test_file_size_gb}
#         - Multipart Threshold (MB): {multipart_threshold_mb}
#         - Chunk Size (MB): {multipart_chunksize_mb}
#         - Max Concurrency: {max_concurrency}
#         """)
#         .batch(
#             bucket_name=bucket_dropdown,
#             test_file_size_gb=mo.ui.number(start=0, stop=1000, step=10, value=10),  # type: ignore
#             multipart_threshold_mb=mo.ui.number(start=1, stop=1000, value=50),  # type: ignore
#             multipart_chunksize_mb=mo.ui.number(start=1, stop=1000, value=50),  # type: ignore
#             max_concurrency=mo.ui.slider(1, 100, value=32, show_value=True),  # type: ignore
#         )
#         .form(submit_button_label="Run Upload Test", clear_on_submit=False)
#     )
#     upload_form
#     return (upload_form,)


# @app.cell(hide_code=True)
# def _(run_s3_upload_test, storage: ObjectStorage, upload_form):
#     if upload_form.value:
#         run_s3_upload_test(
#             storage=storage,
#             **upload_form.value,
#         )
#     return


# @app.cell(hide_code=True)
# def _(bucket_name):
#     def run_s3_upload_test(
#         storage: ObjectStorage,
#         bucket_name: str,
#         test_file_size_gb: float = 1.0,
#         multipart_threshold_mb: int = 8,
#         multipart_chunksize_mb: int = 8,
#         max_concurrency: int = 10,
#     ):
#         from boto3.s3.transfer import TransferConfig

#         if not bucket_name:
#             print("bucket_name is required")
#             return

#         test_dir = "/tmp/bandwidth-test"
#         os.makedirs(test_dir, exist_ok=True)
#         file_size_bytes = int(test_file_size_gb * 1024 * 1024 * 1024)
#         test_file = f"{test_dir}/{test_file_size_gb}G"
#         if not os.path.exists(test_file):
#             print(f"Creating test file: {test_file_size_gb}G...")
#             chunk_size = 64 * 1024 * 1024  # 64 MB
#             zero_chunk = b"\0" * chunk_size
#             with open(test_file, "wb") as f:
#                 remaining = file_size_bytes
#                 while remaining > 0:
#                     write_size = min(chunk_size, remaining)
#                     f.write(zero_chunk[:write_size])
#                     remaining -= write_size
#                     progress = (file_size_bytes - remaining) / file_size_bytes * 100
#                     print(f"Progress: {progress:.0f}%")
#         else:
#             print(f"Test file '{test_file}' already exists locally, proceeding to upload.")

#         transfer_config = TransferConfig(
#             multipart_threshold=multipart_threshold_mb * 1024 * 1024,
#             multipart_chunksize=multipart_chunksize_mb * 1024 * 1024,
#             max_concurrency=max_concurrency,
#             use_threads=True,
#         )
#         file_key = f"benchmark/{test_file_size_gb}G"

#         print(f"""
#         --- S3 Upload Test (Boto3) ---
#         Bucket: s3://{bucket_name}
#         Key: {file_key}
#         Multipart Threshold: {multipart_threshold_mb} MB
#         Chunk Size: {multipart_chunksize_mb} MB
#         Max Concurrency: {max_concurrency}
#         --- S3 Upload Test (Boto3) ---
#         """)

#         start = time.time()
#         try:
#             print("Starting upload...")
#             storage.s3_client.upload_file(test_file, bucket_name, file_key, Config=transfer_config)
#             elapsed = time.time() - start

#             size_bytes = os.path.getsize(test_file)
#             size_gb = size_bytes / (1024 * 1024 * 1024)
#             size_mb = size_bytes / (1024 * 1024)
#             bandwidth_mbs = size_mb / elapsed
#             bandwidth_gbps = (size_bytes * 8) / elapsed / 1_000_000_000

#             print(f"""
#         --- S3 Upload Stats ---
#         Size: {size_gb:.2f} GB
#         Time: {elapsed:.2f} seconds
#         Bandwidth: {bandwidth_mbs:.2f} MB/s ({bandwidth_gbps:.2f} Gbps)
#         --- S3 Upload Stats ---
#         """)
#         except Exception as e:
#             print(f"Upload failed: {e}")
#         return file_key

#     return (run_s3_upload_test,)


# @app.cell(hide_code=True)
# def _(storage: ObjectStorage, bucket_dropdown: mo.ui.dropdown):
#     selected_bucket = bucket_dropdown.value

#     if selected_bucket:
#         objects_result = storage.list_objects(selected_bucket, prefix="benchmark/")
#         object_keys = [obj["Key"] for obj in objects_result["objects"]]

#         if object_keys:
#             object_key_dropdown = mo.ui.dropdown(
#                 options=object_keys, value=object_keys[0] if object_keys else "", label="Select Object Key"
#             )
#             _ui = mo.md(f"""
#             **Available objects in `{selected_bucket}`:**

#             {object_key_dropdown}

#             Found {len(object_keys)} object(s) with prefix 'benchmark/'
#             """)
#         else:
#             object_key_dropdown = None
#             _ui = mo.md(f"""
#             /// admonition | No Objects Found
#                 type: warning

#             No objects found in bucket `{selected_bucket}` with prefix 'benchmark/'.
#             Upload a file first using the upload test above.
#             ///
#             """)
#     else:
#         object_key_dropdown = None
#         object_keys = []
#         _ui = mo.md("""
#         /// admonition | Select a Bucket
#             type: info

#         Please select a bucket above to view available objects for download testing.
#         ///
#         """)

#     _ui
#     return object_key_dropdown, object_keys, selected_bucket


# @app.cell(hide_code=True)
# def _(bucket_dropdown: mo.ui.dropdown, object_key_dropdown: mo.ui.dropdown):
#     if object_key_dropdown is not None:
#         download_form = (
#             mo.md("""
#             ### Configure S3 Download Test
#             - Bucket: {bucket_name}
#             - Object Key: {object_key}
#             - Multipart Threshold (MB): {multipart_threshold_mb}
#             - Chunk Size (MB): {multipart_chunksize_mb}
#             - Max Concurrency: {max_concurrency}
#             """)
#             .batch(
#                 bucket_name=bucket_dropdown,  # type: ignore
#                 object_key=object_key_dropdown,  # type: ignore
#                 multipart_threshold_mb=mo.ui.number(start=1, stop=1000, value=50),  # type: ignore
#                 multipart_chunksize_mb=mo.ui.number(start=1, stop=1000, value=50),  # type: ignore
#                 max_concurrency=mo.ui.slider(1, 100, value=32, show_value=True),  # type: ignore
#             )
#             .form(submit_button_label="Run Download Test", clear_on_submit=False)
#         )
#         _ui = download_form
#     else:
#         download_form = None
#         _ui = mo.md("""
#         /// admonition | No Objects Available
#             type: warning

#         No objects available for download. Please select a bucket and upload a file first using the upload test above.
#         ///
#         """)

#     _ui
#     return (download_form,)


# @app.cell(hide_code=True)
# def _(download_form, run_s3_download_test, storage: ObjectStorage):
#     if download_form and download_form.value:
#         run_s3_download_test(
#             storage=storage,
#             **download_form.value,
#         )
#     return


# @app.cell(hide_code=True)
# def _():
#     def run_s3_download_test(
#         storage: ObjectStorage,
#         bucket_name: str,
#         object_key: str,
#         multipart_threshold_mb: int = 8,
#         multipart_chunksize_mb: int = 8,
#         max_concurrency: int = 10,
#     ):
#         from boto3.s3.transfer import TransferConfig

#         if not bucket_name or not object_key:
#             print("bucket_name and object_key are required")
#             return

#         test_dir = "/tmp/bandwidth-test"
#         os.makedirs(test_dir, exist_ok=True)

#         # Extract filename from object_key for local storage
#         filename = os.path.basename(object_key)
#         output_path = f"{test_dir}/{filename}"

#         transfer_config = TransferConfig(
#             multipart_threshold=multipart_threshold_mb * 1024 * 1024,
#             multipart_chunksize=multipart_chunksize_mb * 1024 * 1024,
#             max_concurrency=max_concurrency,
#             use_threads=True,
#         )

#         print(f"""
#         --- S3 Download Test (Boto3) ---
#         Bucket: s3://{bucket_name}
#         Key: {object_key}
#         Multipart Threshold: {multipart_threshold_mb} MB
#         Chunk Size: {multipart_chunksize_mb} MB
#         Max Concurrency: {max_concurrency}
#         --- S3 Download Test (Boto3) ---
#         """)

#         start = time.time()
#         try:
#             print("Starting download...")
#             storage.s3_client.download_file(bucket_name, object_key, output_path, Config=transfer_config)
#             elapsed = time.time() - start

#             size_bytes = os.path.getsize(output_path)
#             size_gb = size_bytes / (1024 * 1024 * 1024)
#             size_mb = size_bytes / (1024 * 1024)
#             bandwidth_mbs = size_mb / elapsed
#             bandwidth_gbps = (size_bytes * 8) / elapsed / 1_000_000_000

#             print(f"""
#         --- S3 Download Stats ---
#         Size: {size_gb:.2f} GB
#         Time: {elapsed:.2f} seconds
#         Bandwidth: {bandwidth_mbs:.2f} MB/s ({bandwidth_gbps:.2f} Gbps)
#         --- S3 Download Stats ---
#         """)
#         except Exception as e:
#             print(f"Download failed: {e}")

#     return (run_s3_download_test,)


if __name__ == "__main__":
    app.run()
