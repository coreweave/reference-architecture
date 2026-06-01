# SPDX-FileCopyrightText: Copyright (c) 2026 CoreWeave. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Demo container — single-stage build on top of NVIDIA's NGC PyTorch base.
#
# Follows the "Quickstart from the Recommended Base Image" path documented in
# NVIDIA's cosmos-framework setup guide
# (https://github.com/NVIDIA/cosmos-framework/blob/main/docs/setup.md): start
# from the NGC PyTorch container, apt-install a few system deps, install uv,
# run `uv sync --group=cu128-train`, then layer marimo + kubectl + the demo
# assets on top.
#
# Pinned to nvcr.io/nvidia/pytorch:25.06-py3 (CUDA 12 lineage) for RTX Pro 6000
# Blackwell (sm_120) which is validated against `cu128-train`. The newer
# 25.09-py3 tag ships CUDA 13 and would require the `cu130-train` group — works
# on aarch64 / H200 today, untested for sm_120 on amd64. Bump when validated.
#
# Build context: a local clone of NVIDIA/cosmos-framework that the demo
# overlay has been staged into as a `demo/` subdirectory:
#
#   # 1. Clone cosmos-framework
#   git clone https://github.com/NVIDIA/cosmos-framework.git /tmp/build-cf
#
#   # 2. Stage the chart's demo assets into /tmp/build-cf/demo/
#   rsync -a physical-ai/cosmos3/{prompts,marimo,configs,scripts} /tmp/build-cf/demo/
#
#   # 3. One docker build, cosmos-framework as build context, this Dockerfile
#   docker buildx build --platform linux/amd64 \
#     -f physical-ai/cosmos3/Dockerfile \
#     -t "$IMG" --push /tmp/build-cf
#
# --platform linux/amd64 is required: CoreWeave nodes are amd64; default builds
# on Apple Silicon produce arm64 images that Pods reject.
#
# NGC PyTorch images are publicly pullable but require accepting NVIDIA's NGC
# terms once per Docker daemon — see https://catalog.ngc.nvidia.com/orgs/nvidia/containers/pytorch.

ARG NGC_PYTORCH_TAG=25.06-py3
FROM nvcr.io/nvidia/pytorch:${NGC_PYTORCH_TAG} AS base
ENV DEBIAN_FRONTEND=noninteractive

# System deps per cosmos-framework's docs/setup.md quickstart.
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt \
    apt-get update && apt-get install -y --no-install-recommends \
        curl ffmpeg git-lfs libx11-dev tree wget

# Install uv (Python package manager cosmos-framework's pyproject.toml uses).
COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /uvx /usr/local/bin/
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_CACHE_DIR=/root/.cache/uv/python

WORKDIR /workspace

# Bring in cosmos-framework's lockfile + pyproject + packages/ (editable deps)
# before sync, then run the cu128-train uv sync. Mirrors NVIDIA's quickstart
# but with --no-install-project so the editable install of cosmos-framework
# itself happens in a separate, smaller layer after the source is copied.
COPY .python-version pyproject.toml uv.lock /workspace/
COPY packages/ /workspace/packages/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --all-extras --group=cu128-train --frozen

# Demo-only Python deps on top of the cosmos-framework venv. uv won't break
# the cosmos-framework install if anything conflicts.
RUN --mount=type=cache,target=/root/.cache/uv \
    /workspace/.venv/bin/uv pip install marimo httpx kubernetes

# kubectl for the marimo notebook's orchestration cells.
ARG KUBECTL_VERSION=v1.31.0
RUN curl -L "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl

# Bake the cosmos-framework source + install editable so `import cosmos_framework`
# works in K8s Pods (no bind-mount available at runtime).
COPY cosmos_framework/ /workspace/cosmos_framework/
COPY inputs/ /workspace/inputs/
RUN /workspace/.venv/bin/uv pip install --no-deps -e .

# Demo assets — chart-shipped configs, prompts, notebook, build scripts.
COPY demo/ /workspace/demo/

# Put the venv ahead of system paths so `python -m cosmos_framework.X` resolves
# without explicit /workspace/.venv/bin/ prefixing.
ENV PATH="/workspace/.venv/bin:$PATH"
ENV VIRTUAL_ENV=/workspace/.venv
