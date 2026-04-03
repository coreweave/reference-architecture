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

    from lib.remote_execution_helpers import shell
    from lib.k8s import K8s

    TEST_NAMES = {                                                                                                                                                                                                                         
    "gb300-4x":        "nccl-test-distributed-gb200-nvl72-enroot.slurm",
    "gb300-4x-e":      "nccl-test-distributed-gb300-roce-nvl72-enroot.slurm",
    "gb200-4x":        "nccl-test-distributed-gb200-nvl72-enroot.slurm",
    "b300-8x":         "nccl-test-distributed-h100-64.slurm",
    "b200-8x":         "nccl-test-distributed-h100-64.slurm",
    "gd-8xh200ib-i128":"nccl-test-distributed-h100-64.slurm",
    "gd-8xh100ib-i128":"nccl-test-distributed-h100-64.slurm",
    "gd-8xa100-i128":  "nccl-test-distributed-a100-64.slurm",
    # L40S, L40, GH200, RTX Pro 6000 — no matching nccl test script                                                                                                                                                                               
}

    return mo, shell, K8s, TEST_NAMES

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
    shell("sinfo")
    return


@app.cell
def _(shell):
    # Slurm user info:
    shell("sacctmgr show users")
    return


@app.cell
def _(shell):
    # Slurm accounting info:
    shell("sacctmgr show associations format=User,Account,Partition,QOS")
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
    shell("scontrol show nodes")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Partitions (Queues)
    """)
    return


@app.cell
def _(shell):
    shell("scontrol show partition")
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
def _(mo, K8s):
    k8s = K8s()
    nodes = k8s.nodes
    gpu_nodes = nodes.get("gpu") or {}
    gpu_keys = list(gpu_nodes.keys())
    if not gpu_keys:
        gpu_keys = ["(no GPU nodes detected)"]
    default_node_type = gpu_keys[0]
    node_type_dropdown = mo.ui.dropdown(
        options=gpu_keys, value=default_node_type, label="Node type"
    )
    _gpu_type_ui = mo.md(
        f"**GPU node types (from cluster API)**\n\n{node_type_dropdown}"
    )
    _gpu_type_ui
    return (node_type_dropdown,)

@app.cell(hide_code=True)
def _(mo):
    submit_btn = mo.ui.run_button(label="Submit NCCL Test Job")
    submit_btn
    return (submit_btn,)


@app.cell
def _(
    mo,
    num_nodes,
    shell,
    submit_btn,
    node_type_dropdown: mo.ui.dropdown,
    TEST_NAMES,
):
    if submit_btn.value:
        if node_type_dropdown.value not in TEST_NAMES:
            print(f"No NCCL slurm script mapped for node type {node_type_dropdown.value!r}.")
        else:
            script = TEST_NAMES[node_type_dropdown.value]
            cmd = f"cd /mnt/data/arena/benchmarks/nccl/nccl-tests/slurm && sbatch -N {num_nodes.value} {script}"
            print(f"Running: sbatch -N {num_nodes.value} ...")
            shell(cmd)
    else:
        print("Click 'Submit NCCL Test Job' to run the benchmark")
    return


@app.cell
def _(shell):
    shell("squeue")
    return


@app.cell
def _(shell):
    shell("ls /mnt/data/arena/benchmarks/nccl/nccl-tests/slurm/*.out")
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
