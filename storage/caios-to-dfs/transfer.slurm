#!/bin/bash
###
#SBATCH --job-name=caios-vast-transfer
#SBATCH --nodes=8
#SBATCH --ntasks-per-node=8
#SBATCH --cpus-per-task=14
#SBATCH --output="%x_out.%j"
#SBATCH --exclusive

# Log the assigned nodes
echo "Using nodes: $SLURM_JOB_NODELIST"

srun --mpi=pmix --container-image=bitnami/rclone:latest \
        --no-container-remap-root \
        --container-mounts=/mnt/home:/mnt/home,/mnt/data:/mnt/data \
        bash "$WORK_DIR/copy.sh"
