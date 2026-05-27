# SPDX-FileCopyrightText: Copyright (c) 2026 CoreWeave. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Demo container — thin overlay on the upstream cosmos3 base image.
# Pinned to CUDA 12.8 for RTX Pro 6000 Blackwell (sm_120), matching uv group
# `cu128-train` (nvcr.io/nvidia/pytorch:25.11-py3 lineage).
#
# Two-stage build. The base image is built from a clone of the upstream repo
# (nvidia-cosmos/cosmos3-ea-external) rather than replicated here, so NVIDIA's
# Dockerfile stays the single source of truth for the cu128-train dep chain.
#
#   # Stage 1 — upstream base (~7 min). From a cosmos3-ea-external clone:
#   docker buildx build --platform linux/amd64 \
#     --build-arg CUDA_VERSION=12.8.1 \
#     -t cosmos3-base:cu128 --load .
#
#   # Stage 2 — demo overlay (~2 min). From this reference-architecture clone,
#   # with the cosmos3-ea-external clone as the build context (it provides
#   # cosmos3/, packages/, inputs/, pyproject.toml that this Dockerfile COPYs):
#   docker buildx build --platform linux/amd64 \
#     -f physical-ai/cosmos3/Dockerfile \
#     -t "$IMG" --push /path/to/cosmos3-ea-external
#
# --platform linux/amd64 is required: CoreWeave nodes are amd64; a default
# build on Apple Silicon produces arm64 images that Pods reject.

ARG CUDA_VERSION=12.8.1
FROM cosmos3-base:cu128 AS base

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
