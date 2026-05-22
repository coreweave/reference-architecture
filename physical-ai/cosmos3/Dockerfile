# SPDX-FileCopyrightText: Copyright (c) 2026 CoreWeave. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Demo container — thin extension of the repo Dockerfile.
# Pinned to CUDA 12.8 for RTX Pro 6000 Blackwell (sm_120) — matches uv group `cu128`
# which corresponds to nvcr.io/nvidia/pytorch:25.11-py3.
#
# Build from repo root:
#   docker build -f Dockerfile -t cwnnadkarni/cosmos3-demo:0.9 \
#     --build-arg CUDA_VERSION=12.8.1 .

ARG CUDA_VERSION=12.8.1
FROM cosmos3-base:cu128 AS base

# The line above expects the repo image to already be built. If not, build it
# inline by replacing FROM with:
#   FROM nvidia/cuda:${CUDA_VERSION}-cudnn-devel-ubuntu24.04
# and copying in the repo Dockerfile's `uv sync` steps. Easier in practice:
#
#   # First build the repo base:
#   just docker-cu128   # tags as the just-default name; retag to cosmos3-base:cu128
#   docker build -f Dockerfile -t cwnnadkarni/cosmos3-demo:0.9 .

# Demo-only additions on top of the repo venv at /workspace/.venv.
# Let uv resolve transitive deps (jinja2, click, starlette, etc. for marimo).
# uv refuses to break the cosmos3 install if anything conflicts.
RUN --mount=type=cache,target=/root/.cache/uv \
    /workspace/.venv/bin/uv pip install \
      marimo \
      httpx \
      kubernetes

# kubectl for orchestration cells in the marimo notebook
RUN curl -L "https://dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl

# Bake the cosmos3 source into the image so `import cosmos3` works in K8s.
# The repo Dockerfile installs deps via --no-install-project; the justfile
# normally bind-mounts the source at runtime, which K8s Pods can't do.
COPY pyproject.toml /workspace/pyproject.toml
COPY cosmos3/      /workspace/cosmos3/
COPY packages/     /workspace/packages/
COPY inputs/       /workspace/inputs/
RUN /workspace/.venv/bin/uv pip install --no-deps -e .

# Demo assets (configs, prompts, notebook, k8s manifests for self-introspection)
COPY demo/ /workspace/demo/

# Keep the repo entrypoint (sets LD_LIBRARY_PATH='' and activates the venv)
