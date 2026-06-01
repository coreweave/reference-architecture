# SPDX-FileCopyrightText: Copyright (c) 2026 CoreWeave. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Demo container — thin overlay on the upstream cosmos-framework base image.
# Pinned to CUDA 12.8 for RTX Pro 6000 Blackwell (sm_120), matching uv group
# `cu128-train` (nvcr.io/nvidia/pytorch:25.11-py3 lineage).
#
# Two-stage build. The base image is built from a clone of the upstream repo
# (NVIDIA/cosmos-framework) rather than replicated here, so NVIDIA's Dockerfile
# stays the single source of truth for the cu128-train dep chain.
#
#   # Stage 1 — upstream base (~7 min). From a NVIDIA/cosmos-framework clone:
#   docker buildx build --platform linux/amd64 \
#     --build-arg CUDA_VERSION=12.8.1 \
#     -t cosmos-framework-base:cu128 --load .
#
#   # Stage 2 — demo overlay (~2 min). From this reference-architecture clone,
#   # with the cosmos-framework clone as the build context (it provides
#   # cosmos_framework/, packages/, inputs/, pyproject.toml that this Dockerfile COPYs):
#   docker buildx build --platform linux/amd64 \
#     -f physical-ai/cosmos3/Dockerfile \
#     -t "$IMG" --push /path/to/cosmos-framework
#
# --platform linux/amd64 is required: CoreWeave nodes are amd64; a default
# build on Apple Silicon produces arm64 images that Pods reject.

ARG CUDA_VERSION=12.8.1
FROM cosmos-framework-base:cu128 AS base

# Put the cosmos-framework venv ahead of system paths so `python -m cosmos_framework.X`
# resolves without explicit /workspace/.venv/bin/ prefixing. Upstream's Dockerfile
# creates the venv but doesn't set PATH; the EA cosmos3-base image did, so this is
# an explicit equivalent for the public release.
ENV PATH="/workspace/.venv/bin:$PATH"
ENV VIRTUAL_ENV=/workspace/.venv

# Demo-only additions on top of the repo venv at /workspace/.venv.
# Let uv resolve transitive deps (jinja2, click, starlette, etc. for marimo).
# uv refuses to break the cosmos-framework install if anything conflicts.
RUN --mount=type=cache,target=/root/.cache/uv \
    /workspace/.venv/bin/uv pip install \
      marimo \
      httpx \
      kubernetes

# kubectl for orchestration cells in the marimo notebook
ARG KUBECTL_VERSION=v1.31.0
RUN curl -L "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl

# Bake the cosmos-framework source into the image so `import cosmos_framework`
# works in K8s. The repo Dockerfile installs deps via --no-install-project;
# the justfile normally bind-mounts the source at runtime, which K8s Pods can't do.
COPY pyproject.toml cosmos_framework/ packages/ inputs/ /workspace/
RUN /workspace/.venv/bin/uv pip install --no-deps -e .

# Demo assets (configs, prompts, notebook, k8s manifests for self-introspection)
COPY demo/ /workspace/demo/

# Keep the repo entrypoint (sets LD_LIBRARY_PATH='' and activates the venv)
