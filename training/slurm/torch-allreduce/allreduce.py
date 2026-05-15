"""
Simple PyTorch Distributed All‑Reduce Script (env vars provided by Slurm)
------------------------------------------------------------------------
This script assumes the following environment variables are **already** set
by the Slurm launch wrapper **before** `python` is invoked:

* `MASTER_ADDR`, `MASTER_PORT`      - rendezvous endpoint for NCCL

Submit with the accompanying `allreduce.sbatch` example.
"""

import logging
import os

import torch
import torch.distributed as dist

# -----------------------------------------------------------------------------
# Logging - emit INFO only on rank 0 to avoid duplication
# -----------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
if int(os.getenv("SLURM_PROCID", "0")) != 0:
    logger.setLevel(logging.WARNING)


# -----------------------------------------------------------------------------
# Main collective logic
# -----------------------------------------------------------------------------


def main() -> None:
    # Set the torch env vars from Slurm's env vars. One Slurm task = one rank
    # = one GPU; the sbatch sets --ntasks-per-node to the number of GPUs.
    rank = int(os.environ["SLURM_PROCID"])
    os.environ["RANK"] = str(rank)

    world_size = int(os.environ["SLURM_NTASKS"])
    os.environ["WORLD_SIZE"] = str(world_size)

    local_rank = int(os.environ["SLURM_LOCALID"])
    os.environ["LOCAL_RANK"] = str(local_rank)

    # These were already set by the sbatch script
    master_addr = os.environ["MASTER_ADDR"]
    master_port = int(os.environ["MASTER_PORT"])

    logger.info(
        "Initializing process group (backend=nccl, master_addr=%s, master_port=%d)...",
        master_addr,
        master_port,
    )
    dist.init_process_group(backend="nccl", init_method="env://")
    logger.info("Process group ready. Rank %d of %d", rank, world_size)

    torch.cuda.set_device(local_rank)
    logger.info("Pinned to CUDA device %d", local_rank)

    # Create a tensor containing *rank* and perform an all-reduce (SUM)
    tensor = torch.tensor([rank], device="cuda")
    logger.debug("Tensor before all-reduce: %s", tensor.item())

    logger.info("Performing all-reduce (SUM):")
    dist.all_reduce(tensor, op=dist.ReduceOp.SUM)

    logger.info(
        "All-reduce complete. Result on rank %d: %d (expected %d)",
        rank,
        tensor.item(),
        world_size * (world_size - 1) // 2,
    )

    logger.info("Destroying process group and exiting.")
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
