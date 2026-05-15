#!/bin/bash
#
# Simple Slurm batch script to launch the PyTorch distributed all-reduce example.
# Save as allreduce.sbatch and submit with:
#     sbatch allreduce.sbatch
#
# ---------------- Slurm directives ----------------
#SBATCH --job-name=torch-allreduce
#SBATCH --nodes=16                # adjust as needed
#SBATCH --exclusive
#SBATCH --ntasks-per-node=1
#SBATCH --time=00:10:00
# --------------------------------------------------
set -euo pipefail

# --------------------------------------------------
# Set the typical CW NCCL env vars.
# --------------------------------------------------

# Find the latest at CoreWeave's nccl-tests github repo
export NCCL_SOCKET_IFNAME=eth0
export NCCL_IB_HCA=ibp
export UCX_NET_DEVICES=ibp0:1,ibp1:1,ibp2:1,ibp3:1
export SHARP_COLL_ENABLE_PCI_RELAXED_ORDERING=1
export NCCL_COLLNET_ENABLE=0

export NVIDIA_IMEX_CHANNELS=0
export NCCL_NET_GDR_C2C=1
export PMIX_MCA_gds='^ds12'

# --------------------------------------------------
# Container image
# --------------------------------------------------
# You can override the container image by exporting CONTAINER_IMAGE before
# submission or by editing the variable below.
#
# To avoid cold‑pull delays, first save the image locally and point to the
# resulting SquashFS on DFS, e.g.
#   srun --container-save /mnt/vast/images/torch-extras.sqsh \
#        --container-image=ghcr.io#coreweave/ml-containers/torch-extras:es-torch-v2.7.0-106e5d6-base-cuda12.8.1-ubuntu22.04-torch2.7.0-vision0.22.0-audio2.7.0-abi1 hostname
#   export CONTAINER_IMAGE=/mnt/vast/images/torch-extras.sqsh
CONTAINER_IMAGE="${CONTAINER_IMAGE:-ghcr.io#coreweave/ml-containers/torch-extras:es-cuda-12.9.1-74755e9-nccl-cuda12.9.1-ubuntu22.04-nccl2.27.5-1-torch2.7.1-vision0.22.1-audio2.7.1-abi1}"

# -----------------------------------------------------------------------------
# Derive the variables that PyTorch's NCCL backend expects from Slurm's runtime.
# -----------------------------------------------------------------------------
# Use the first host in the allocation as the rendez-vous master address
export MASTER_ADDR=$(scontrol show hostnames "$SLURM_NODELIST" | head -n1)

# Use a port correlated to the job ID, in the range of 20000-29999.
export MASTER_PORT=$((20000 + SLURM_JOB_ID % 10000))

echo "MASTER_ADDR=$MASTER_ADDR  MASTER_PORT=$MASTER_PORT"

# --------------------------------------------------
# Launch job via srun (containerized)
# --------------------------------------------------

# Absolute path to the example script (same directory as this sbatch file)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Launching job with srun..."
srun --container-image=${CONTAINER_IMAGE} --container-mounts=/mnt:/mnt python ${SCRIPT_DIR}/allreduce.py
