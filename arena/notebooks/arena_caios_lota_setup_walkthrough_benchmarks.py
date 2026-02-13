import marimo

__generated_with = "0.19.11"
app = marimo.App(width="medium", app_title="CoreWeave ARENA")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![CoreWeave ARENA Banner](public/banner.jpg)
    """)
    return


@app.cell(hide_code=True)
def _():
    import json
    import os
    import time

    import marimo as mo
    from arena.object_storage_helpers import (
        apply_policy,
        list_buckets,
        list_policies,
    )
    from arena.remote_execution_helpers import shell

    return apply_policy, json, list_buckets, list_policies, mo, os, shell, time


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # CoreWeave AI Labs: Object Storage & LOTA

    /// admonition | About This Notebook
        type: info

    This notebook provides a walkthrough for setting up and benchmarking CoreWeave AI Object Storage (CAIOS) and LOTA.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    /// details | Table of Contents

    - **Access Keys** - Create credentials in the console
    - **Organizational Policies** - Set S3 access policies
    - **Bucket Operations** - List and manage buckets
    - **Data Transfer** - Copy data with s5cmd
    - **Benchmarks** - Performance testing
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## Access Keys

    /// attention | Console Setup Required
    Access keys are set up for you in the notebook if pod identity is set up.

    If you'd like to use object storage outside of this pod you'll need to create your Access Key and Secret Access Key in the [CoreWeave Console](https://docs.coreweave.com/docs/products/storage/object-storage/get-started-caios).

    These credentials are used for S3 API access to CAIOS and LOTA.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 2. Set Organizational Policies

    /// admonition | Access Control
        type: info

    Organizational policies control who can access your S3 resources. Define policies using JSON format.

    Reference: [Organization Access Policies](https://docs.coreweave.com/docs/products/storage/object-storage/auth-access/organization-policies/about)
    ///

    /// details | Policy Examples

    **Full S3 API access to all users:**
    ```json
    {
      "policy": {
        "version": "v1alpha1",
        "name": "full-s3-api-access",
        "statements": [
          {
            "name": "allow-full-s3-api-access-to-all",
            "effect": "Allow",
            "actions": ["s3:*"],
            "resources": ["*"],
            "principals": ["*"]
          }
        ]
      }
    }
    ```

    **Read-only access to all buckets:**
    ```json
    {
      "policy": {
        "version": "v1alpha1",
        "name": "s3-read-only-all-buckets",
        "statements": [
          {
            "name": "read-only-access",
            "effect": "Allow",
            "actions": ["s3:List*", "s3:Get*", "s3:Head*"],
            "resources": ["*"],
            "principals": ["*"]
          }
        ]
      }
    }
    ```
    """)
    return


@app.cell
def _(apply_policy):
    apply_policy("""
            {
              "policy": {
                "version": "v1alpha1",
                "name": "test_policy_user_full_access",
                "statements": [
                  {
                    "name": "allow-full-access",
                    "effect": "Allow",
                    "actions": ["s3:*"],
                    "resources": ["*"],
                    "principals": ["role/Admin"]
                  }
                ]
              }
            }
            """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Query Organizational Access Policies
    """)
    return


@app.cell
def _(json, list_policies):
    policies = list_policies()
    print(json.dumps(policies, indent=2))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 3. Bucket Operations

    /// admonition | S3 Buckets
        type: info

    List and manage your S3 buckets. Buckets are the top-level containers for your objects.
    ///
    """)
    return


@app.cell
def _(list_buckets):
    list_buckets()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 4. AWS CLI Configuration

    /// attention | Endpoint Configuration

    Configure the AWS CLI to use CoreWeave endpoints:

    | Service | Endpoint |
    |---------|----------|
    | CAIOS | `https://cwobject.com` |
    | LOTA | `http://cwlota.com` |
    ///
    """)
    return


@app.cell
def _(shell):
    shell("aws configure set s3.addressing_style virtual")
    return


@app.cell
def _(os, shell):
    endpoint = os.environ.get("S3_ENDPOINT_URL", "https://cwobject.com")
    shell(f"aws configure set endpoint_url {endpoint}")
    return


@app.cell
def _(shell):
    shell("aws s3 ls")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 5. Data Transfer with s5cmd

    /// admonition | High-Performance Transfers
        type: success

    Use `s5cmd` for parallel, high-performance S3 transfers. It's significantly faster than the AWS CLI for bulk operations.
    ///

    /// details | s5cmd Examples

    **For a few large files** - Maximize multipart upload parallelism:
    ```bash
    s5cmd --endpoint-url https://cwobject.com \
          --numworkers 4 \
          cp --concurrency 16 's3://source-bucket/*' s3://target-bucket/
    ```

    **For many small files** - Maximize parallel file transfers:
    ```bash
    s5cmd --endpoint-url https://cwobject.com \
          --numworkers 512 \
          cp 's3://source-bucket/*' s3://target-bucket/
    ```
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Download Test

    /// admonition | CoreWeave Speedtest
        type: info

    Using CoreWeave's [speedtest endpoint](https://docs.coreweave.com/docs/platform/regions/general-access/us-east/us-east-01) to measure network bandwidth.

    | File | URL |
    |------|-----|
    | 1GB | `http://http.speedtest.us-east-01.coreweave.com/1G` |
    | 10GB | `http://http.speedtest.us-east-01.coreweave.com/10G` |
    ///
    """)
    return


@app.cell
def _(os, shell, time):
    def run_download_test():
        shell("mkdir -p /tmp/bandwidth-test")
        print("--- Download Test: 10GB file ---\n")

        start = time.time()
        shell(
            "curl -o /tmp/bandwidth-test/10G http://http.speedtest.us-east-01.coreweave.com/10G",
            stream=True,
        )
        elapsed = time.time() - start

        try:
            size_bytes = os.path.getsize("/tmp/bandwidth-test/10G")
            size_gb = size_bytes / (1024 * 1024 * 1024)
            size_mb = size_bytes / (1024 * 1024)
            bandwidth_mbs = size_mb / elapsed
            bandwidth_gbps = (size_bytes * 8) / elapsed / 1_000_000_000

            print("\n📊 Download Stats:")
            print(f"   Size: {size_gb:.2f} GB")
            print(f"   Time: {elapsed:.2f} seconds")
            print(f"   Bandwidth: {bandwidth_mbs:.2f} MB/s ({bandwidth_gbps:.2f} Gbps)")
        except FileNotFoundError:
            print("File not found - download may have failed")

    run_download_test()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Upload with s5cmd

    /// admonition | High-Performance Upload
        type: success

    Upload the 10GB test file to your CoreWeave bucket using s5cmd with parallel multipart uploads.

    Set `CW_BENCHMARK_BUCKET` environment variable to enable.

    📖 [CoreWeave Data Migration Guide](https://docs.coreweave.com/docs/products/storage/object-storage/migrate-data)
    ///

    **Tool comparison:**

    | Tool | Best For | Performance |
    |------|----------|-------------|
    | **s5cmd** | High-performance parallel transfers | ~20-25 Gbps |
    | **Rclone** | Complex sync, multi-cloud transfers | ~10-15 Gbps |

    **s5cmd concurrency options:**

    | Option | Description | Default |
    |--------|-------------|---------|
    | `--numworkers` | Global worker pool size (parallel operations) | 256 |
    | `--concurrency` | Parts uploaded/downloaded in parallel per file | 5 |

    /// admonition | Use CoreWeave fork
        type: warning

    Use the [CoreWeave fork of s5cmd](https://github.com/coreweave/s5cmd/releases) which defaults
    to virtual-style addressing required by AI Object Storage.

    ```bash
    curl -L https://github.com/coreweave/s5cmd/releases/download/v2.3.0-acb67716/s5cmd_2.3.0-acb67716_Linux-64bit.tar.gz -o /tmp/s5cmd.tar.gz
    tar -xzf /tmp/s5cmd.tar.gz -C /usr/local/bin s5cmd
    ```
    ///
    """)
    return


@app.cell
def _(os, shell, time):
    def run_s5cmd_upload_test(numworkers: int = 16, concurrency: int = 32):
        """Upload using s5cmd with configurable parallelism."""
        bucket = os.environ.get("CW_BENCHMARK_BUCKET", "")
        endpoint = os.environ.get("S3_ENDPOINT_URL", "https://cwobject.com")

        if not bucket:
            print("⚠️  Set CW_BENCHMARK_BUCKET environment variable to run upload test")
            print("   Example: export CW_BENCHMARK_BUCKET=my-bucket")
            return

        if not os.path.exists("/tmp/bandwidth-test/10G"):
            print("⚠️  Run the download test first to get the 10GB file")
            return

        print("--- s5cmd Upload Test ---")
        print(f"   Bucket: s3://{bucket}")
        print(f"   Workers: {numworkers} (--numworkers)")
        print(f"   Concurrency: {concurrency} (--concurrency per file)\n")

        start = time.time()
        shell(
            f"""s5cmd --endpoint-url {endpoint} --numworkers {numworkers} \
            cp --concurrency {concurrency} /tmp/bandwidth-test/10G 's3://{bucket}/benchmark/10G'""",
            stream=True,
        )
        elapsed = time.time() - start

        size_bytes = os.path.getsize("/tmp/bandwidth-test/10G")
        size_gb = size_bytes / (1024 * 1024 * 1024)
        size_mb = size_bytes / (1024 * 1024)
        bandwidth_mbs = size_mb / elapsed
        bandwidth_gbps = (size_bytes * 8) / elapsed / 1_000_000_000

        print("\n📊 s5cmd Upload Stats:")
        print(f"   Size: {size_gb:.2f} GB")
        print(f"   Time: {elapsed:.2f} seconds")
        print(f"   Bandwidth: {bandwidth_mbs:.2f} MB/s ({bandwidth_gbps:.2f} Gbps)")

        print("\n🧹 Cleaning up remote file...")
        shell(
            f"s5cmd --endpoint-url {endpoint} rm 's3://{bucket}/benchmark/10G'",
            quiet=True,
        )

    run_s5cmd_upload_test(numworkers=16, concurrency=32)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Upload/Download with Rclone

    /// admonition | Rclone - Versatile Cloud Storage Tool
        type: info

    [Rclone](https://rclone.org/) is a versatile tool for managing files across cloud storage providers.
    Best for complex sync operations and transfers between diverse cloud providers.

    **Pre-configured:** Rclone is auto-configured with the `coreweave` remote if AWS credentials are set.

    📖 [CoreWeave Data Migration Guide](https://docs.coreweave.com/docs/products/storage/object-storage/migrate-data)
    ///

    /// admonition | Warning
        type: danger

    **Do not use Rclone with Local Storage** - known kernel panic issues. Use s5cmd instead.
    ///

    **Rclone optimization flags:**

    | Flag | Description | Recommended |
    |------|-------------|-------------|
    | `--transfers` | Concurrent file transfers | 64 |
    | `--checkers` | Concurrent file checks | 128 |
    | `--s3-chunk-size` | Chunk size for multipart | 50M |
    | `--s3-upload-concurrency` | Parts per file in parallel | 10 |

    **RAM estimation:** `transfers × (upload-concurrency × (chunk-size + buffer-size))`
    """)
    return


@app.cell
def _(os, shell, time):
    def run_rclone_upload_test(transfers: int = 64, upload_concurrency: int = 10, chunk_size_mb: int = 50):
        """Upload using rclone with optimized settings for CoreWeave."""
        bucket = os.environ.get("CW_BENCHMARK_BUCKET", "")

        if not bucket:
            print("⚠️  Set CW_BENCHMARK_BUCKET environment variable to run upload test")
            print("   Example: export CW_BENCHMARK_BUCKET=my-bucket")
            return

        if not os.path.exists("/tmp/bandwidth-test/10G"):
            print("⚠️  Run the download test first to get the 10GB file")
            return

        # Check if rclone is configured (auto-configured in startup.sh if AWS credentials available)
        result = shell("rclone listremotes 2>/dev/null || echo ''", quiet=True)
        if "coreweave:" not in result:
            print("⚠️  Rclone 'coreweave' remote not configured.")
            print("   This is auto-configured if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are set.")
            print("   Or manually add to ~/.config/rclone/rclone.conf:")
            print("""
    [coreweave]
    type = s3
    provider = Other
    access_key_id = YOUR_ACCESS_KEY
    secret_access_key = YOUR_SECRET_KEY
    endpoint = https://cwobject.com
    force_path_style = false
    no_check_bucket = true
    """)
            return

        remote = "coreweave:"

        print("--- Rclone Upload Test ---")
        print(f"   Transfers: {transfers}")
        print(f"   Upload Concurrency: {upload_concurrency}")
        print(f"   Chunk Size: {chunk_size_mb}M\n")

        start = time.time()
        shell(
            f"""rclone copy /tmp/bandwidth-test/10G {remote}{bucket}/benchmark/ \
            --progress \
            --stats 5s \
            --transfers {transfers} \
            --s3-chunk-size {chunk_size_mb}M \
            --s3-upload-concurrency {upload_concurrency}""",
            stream=True,
        )
        elapsed = time.time() - start

        size_bytes = os.path.getsize("/tmp/bandwidth-test/10G")
        size_gb = size_bytes / (1024 * 1024 * 1024)
        bandwidth_mbs = size_bytes / (1024 * 1024) / elapsed
        bandwidth_gbps = (size_bytes * 8) / elapsed / 1_000_000_000

        print("\n📊 Rclone Upload Stats:")
        print(f"   Size: {size_gb:.2f} GB")
        print(f"   Time: {elapsed:.2f} seconds")
        print(f"   Bandwidth: {bandwidth_mbs:.2f} MB/s ({bandwidth_gbps:.2f} Gbps)")

        # Cleanup
        print("\n🧹 Cleaning up remote file...")
        shell(f"rclone delete {remote}{bucket}/benchmark/10G", quiet=True)

    # Uncomment to run rclone test (requires rclone configuration)
    # run_rclone_upload_test(transfers=64, upload_concurrency=10, chunk_size_mb=50)
    print("ℹ️  Rclone test available - configure rclone and uncomment to run")
    return


@app.cell
def _(shell):
    # Cleanup local test file
    shell("rm -rf /tmp/bandwidth-test", quiet=True)
    print("✓ Cleaned up local test files")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 6. Benchmark Performance

    /// admonition | Performance Testing
        type: info

    CoreWeave SA team can help you run benchmarks to measure throughput and latency for your storage configuration.
    Published Benchmarks:
    - [DFS Benchmark](https://www.coreweave.com/blog/storage-benchmarking-distributed-file-storage)
    - [CAIOS/LOTA Benchmark](https://www.coreweave.com/blog/caios-achieves-7-gb-s-per-gpu-on-nvidia-blackwell-ultra)
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## Scratchpad

    /// details | Scratchpad
        type: info

    Use the cell below for experimentation and quick tests.
    ///
    """)
    return


@app.cell
def _():
    # Scratchpad - use for experimentation
    pass
    return


if __name__ == "__main__":
    app.run()
