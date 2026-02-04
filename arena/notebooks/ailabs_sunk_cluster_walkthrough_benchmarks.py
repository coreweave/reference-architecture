import marimo

__generated_with = "0.19.4"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # CoreWeave AI Labs
    """)
    return


@app.cell(hide_code=True)
def _():
    # setup cell runs before anything else, recommend putting values in here
    import marimo as mo

    """
    Import SSH helpers from ailabs library.

    Configuration via environment variables:
        CW_AILABS_SSH_KEY_PATH: Path to SSH private key (default: /root/.ssh/id_rsa)
        CW_AILABS_SSH_HOST: SSH host (e.g., user+tenant@sunk.tenant.coreweave.app)
    """
    from ailabs.remote_execution_helpers import ssh, run_remote, ssh_command
    return mo, ssh


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## SUNK / Slurm Cluster walkthrough and benchmarks:

    - [Inspect your SUNK Slurm cluster](#inspect-your-sunk-slurm-cluster)
    - [Run NCCL tests](#run-nccl-tests)
    - [Job Observability and Grafana Dashboards](#job-observability-and-grafana-dashboards)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Inspect your SUNK Slurm cluster
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### [Node types](https://docs.coreweave.com/docs/platform/instances/gpu-instances)
    """)
    return


@app.cell
def _(ssh):
    # Slurm cluster info:
    print(ssh("sinfo"))
    return


@app.cell
def _(ssh):
    # Slurm user info:
    print(ssh("sacctmgr show users"))
    return


@app.cell
def _(ssh):
    # Slurm accounting info:
    print(ssh("sacctmgr show associations format=User,Account,Partition,QOS"))
    return


@app.cell
def _(ssh):
    # Node info
    print(ssh("scontrol show nodes"))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Default queues
    """)
    return


@app.cell
def _(ssh):
    print(ssh("scontrol show partition"))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Run NCCL tests<br/>
    We will run [NCCL test](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/usage/collectives.html): ```AllReduce```<br/>
    More information on CoreWeave NCCL tests can be found [here](https://github.com/coreweave/nccl-tests/tree/master)
    """)
    return


@app.cell
def _(ssh):
    print(ssh("cd /mnt/data/ailabs/benchmarks/nccl/nccl-tests/slurm && sbatch -N 2 nccl-test-distributed-h100-64.slurm"))
    return


@app.cell
def _(ssh):
    print(ssh("squeue"))
    return


@app.cell
def _(ssh):
    print(ssh("ls /mnt/data/ailabs/benchmarks/nccl/nccl-tests/slurm/*.out"))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    #### **All Reduce NCCL output:**
    """)
    return


@app.cell
def _(ssh):
    print(ssh("cat $(ls -1 /mnt/data/ailabs/benchmarks/nccl/nccl-tests/slurm/*.out|tail -1)"))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Job Observability and Grafana Dashboards

    SUNK and Slurm Job Observability [walkthrough](https://cks-grafana.coreweave.com/dashboards/f/afaelmrlx0um8b/?orgId=1)
    """)
    return


if __name__ == "__main__":
    app.run()