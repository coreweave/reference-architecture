# NCCL Benchmarks

This directory is a placeholder for NCCL benchmark configurations.

The actual NCCL tests are cloned from the CoreWeave nccl-tests repository:
https://github.com/coreweave/nccl-tests

During container startup, the repository is cloned to the remote login node at:
`/mnt/data/ailabs/benchmarks/nccl/`

## Repository Contents

The nccl-tests repository includes:
- Docker images with NCCL, HPC-X, and related tools
- MPI Operator job manifests for various GPU types (A40, A100, H100, GB200)
- Slurm batch scripts for distributed NCCL testing
- Example configurations for SHARP-enabled runs

## Usage

See the main repository README for running NCCL tests:
https://github.com/coreweave/nccl-tests/blob/master/README.md
