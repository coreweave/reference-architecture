import marimo

__generated_with = "0.19.7"
app = marimo.App(width="medium", app_title="CoreWeave ARENA")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ![CoreWeave ARENA Banner](public/banner.jpg)
    """)
    return


@app.cell(hide_code=True)
def _():
    # setup cell runs before anything else, recommend putting values in here
    import marimo as mo

    """
    Import SSH helpers from arena library.

    Configuration via environment variables:
        CW_ARENA_SSH_KEY_PATH: Path to SSH private key (default: /root/.ssh/id_rsa)
        CW_ARENA_SSH_HOST: SSH host (e.g., user+tenant@sunk.tenant.coreweave.app)
    """
    from arena.remote_execution_helpers import shell

    return mo, shell


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # CoreWeave AI Labs: SUNK Cluster

    /// admonition | About This Notebook
        type: info

    This notebook provides a walkthrough for inspecting and benchmarking your SUNK (Slurm on Kubernetes) cluster.
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    /// details | Table of Contents

    - **Cluster Inspection** - View nodes, partitions, and user info
    - **NCCL Benchmarks** - Run distributed GPU communication tests
    - **Job Observability** - Grafana dashboards and monitoring
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 1. Inspect Your SUNK Slurm Cluster

    /// admonition | Cluster Overview
        type: info

    Use Slurm commands to inspect your cluster configuration, nodes, and users.

    Reference: [CoreWeave GPU Instances](https://docs.coreweave.com/docs/platform/instances/gpu-instances)
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Cluster Info
    """)
    return


@app.cell
def _(shell):
    # Slurm cluster info:
    print(shell("sinfo"))
    return


@app.cell
def _(shell):
    # Slurm user info:
    print(shell("sacctmgr show users"))
    return


@app.cell
def _(shell):
    # Slurm accounting info:
    print(shell("sacctmgr show associations format=User,Account,Partition,QOS"))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Node Details
    """)
    return


@app.cell
def _(shell):
    # Node info
    print(shell("scontrol show nodes"))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Partitions (Queues)
    """)
    return


@app.cell
def _(shell):
    print(shell("scontrol show partition"))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 2. Run NCCL Tests

    /// attention | NCCL Benchmarks

    Running [NCCL AllReduce](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/usage/collectives.html) benchmark to test GPU-to-GPU communication.

    | Test | Description |
    |------|-------------|
    | AllReduce | Sum values across all GPUs |
    | AllGather | Gather data from all GPUs |
    | Broadcast | Send data from one GPU to all |
    ///

    /// admonition | Reference
        type: info

    More information: [CoreWeave NCCL Tests](https://github.com/coreweave/nccl-tests/tree/master)
    ///
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    num_nodes = mo.ui.slider(1, 16, value=2, label="Number of Nodes", show_value=True)
    num_nodes
    return (num_nodes,)


@app.cell(hide_code=True)
def _(mo, num_nodes):
    mo.md(f"""
    **Selected: {num_nodes.value} nodes** ({num_nodes.value * 8} GPUs)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    submit_btn = mo.ui.run_button(label="Submit NCCL Test Job")
    submit_btn
    return (submit_btn,)


@app.cell
def _(num_nodes, shell, submit_btn):
    if submit_btn.value:
        cmd = f"cd /mnt/data/arena/benchmarks/nccl/nccl-tests/slurm && sbatch -N {num_nodes.value} nccl-test-distributed-h100-64.slurm"
        print(f"Running: sbatch -N {num_nodes.value} ...")
        print(shell(cmd))
    else:
        print("Click 'Submit NCCL Test Job' to run the benchmark")
    return


@app.cell
def _(shell):
    print(shell("squeue"))
    return


@app.cell
def _(shell):
    print(shell("ls /mnt/data/arena/benchmarks/nccl/nccl-tests/slurm/*.out"))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### NCCL Test Output

    /// admonition | AllReduce Results
        type: success

    The output below shows bandwidth and latency for the AllReduce collective operation.
    ///
    """)
    return


@app.cell
def _(shell):
    # Stream the NCCL test output (can be large)
    shell(
        "cat $(ls -1 /mnt/data/arena/benchmarks/nccl/nccl-tests/slurm/*.out|tail -1)",
        stream=True,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## 3. Job Observability and Grafana Dashboards

    /// admonition | Monitoring
        type: info

    SUNK and Slurm Job Observability dashboards are available in Grafana.

    :chart_with_upwards_trend: [View Dashboards](https://cks-grafana.coreweave.com/dashboards/f/afaelmrlx0um8b/?orgId=1)
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
