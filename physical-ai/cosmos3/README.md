# Cosmos3 Data Flywheel on CoreWeave

> **Want to jump in?** Read **[TUTORIAL.md](TUTORIAL.md)** — a step-by-step walkthrough of the whole pipeline.

Reference architecture for running **NVIDIA Cosmos3** (a world-foundation model for physical AI / robotics) on **CoreWeave Kubernetes Service**. Covers the full lifecycle:

**synthetic data generation → SFT fine-tuning → DCP→HF export → live serving via Ray Serve → interactive marimo notebook.**

Validated single-node on 8× RTX Pro 6000 Blackwell + VAST CSI. Pure CKS — no SUNK / Slurm, no KubeRay operator. Packaged as a small Helm chart so each pipeline step is a single `values.yaml` flag.

## What's in the box

```
physical-ai/cosmos3/
├── TUTORIAL.md                       # ← start here: step-by-step walkthrough
├── README.md                         # this file
├── Chart.yaml                        # Helm chart metadata
├── values.yaml                       # one entry per pipeline step
├── templates/                        # _helpers.tpl + jobs + prerequisites + serving
├── Dockerfile                        # demo image (extends upstream cosmos-framework, cu128-train)
├── configs/vision_sft_nano.toml      # SFT recipe — lifted from upstream + chart-tunable
├── prompts/                          # seed prompts + programmatic expander
├── scripts/                          # closed-loop JSONL builder
└── marimo/cosmos3_demo.py            # reactive notebook — calls Ray Serve /generate
```

> Tracks the public **[NVIDIA/cosmos-framework](https://github.com/NVIDIA/cosmos-framework)** release (package: `cosmos_framework`). HF models live under the public `nvidia/Cosmos3-*` org.

The chart renders to ~27 K8s resources when every step is enabled. Default is a no-op: enable steps individually with `--set steps.<name>.enabled=true`, or use an overrides file.

## Pipeline at a glance

| Phase | Steps in `values.yaml` | What you get |
|---|---|---|
| **Setup** | `prerequisites` (always-on), build image | PVC + workbench Pod + RBAC + demo container |
| **Stage** | `prefetch`, `convert`, `bridge` | Base model + datasets on the PVC |
| **Smoke** | `smoke` | One ~5-second video confirms the inference chain works |
| **Flywheel** | `generateSynthetic`, `sdgExtra` | Synthetic clips you mix with bridge-v2 |
| **Fine-tune** | `sftSmoke`, then `sft` and/or `sftMixed` | DCP-format checkpoint driven by `configs/vision_sft_nano.toml` |
| **Export + serve** | `export`, `exportMixed`, `rayServe`, `marimo` | HF safetensors, live HTTP endpoint, notebook UI |
| **Compare** | `compare`, `compareMixed`, `compareInDist` | Qualitative side-by-side videos |

Full step list, GPU counts, wraps, and outputs are in **[TUTORIAL.md § Pipeline](TUTORIAL.md#part-4--stage-the-models-and-data-30-minutes-mostly-wait)**.

## Quick reference

The chart has no default container image — you build the `Dockerfile` in this
directory yourself and push to a registry your cluster can pull from. See
[TUTORIAL.md § Build and push the demo image](TUTORIAL.md#step-3-build-and-push-the-demo-image)
for the build pattern. The chart's `Dockerfile` is a single-stage build on top
of `nvcr.io/nvidia/pytorch:25.06-py3` (NVIDIA's recommended NGC PyTorch base
for cosmos-framework, CUDA 12 lineage for sm_120 Blackwell compatibility).
`--platform linux/amd64` is required (CW nodes are amd64).

Once your image is pushed, plumb it through every `helm template` invocation
via `--set image=…`:

```bash
export IMG=<your-registry>/cosmos3-demo:<tag>     # the image you built and pushed
export NS=<your-namespace>

# Render + apply prerequisites only
helm template physical-ai/cosmos3 --set image="$IMG" | kubectl -n "$NS" apply -f -

# Enable one step
helm template physical-ai/cosmos3 --set image="$IMG" \
  --set steps.smoke.enabled=true \
  | kubectl -n "$NS" apply -f -

# Enable everything
helm template physical-ai/cosmos3 --set image="$IMG" \
  --set rayServe.enabled=true --set marimo.enabled=true \
  --set steps.prefetch.enabled=true \
  --set steps.convert.enabled=true \
  --set steps.smoke.enabled=true \
  --set steps.bridge.enabled=true \
  --set steps.libero.enabled=true \
  --set steps.generateSynthetic.enabled=true \
  --set steps.sdgExtra.enabled=true \
  --set steps.sftSmoke.enabled=true \
  --set steps.sft.enabled=true \
  --set steps.sftMixed.enabled=true \
  --set steps.export.enabled=true \
  --set steps.exportMixed.enabled=true \
  --set steps.compare.enabled=true \
  | kubectl -n "$NS" apply -f -
```

Forgetting `--set image=…` fails loud at `helm template` time with a clear
message — beats a Pod stuck in `ImagePullBackOff` 30 seconds later.

## Important gotchas

These are wired into the chart already but worth knowing:

- **`--platform linux/amd64`** — CW nodes are amd64; default `docker build` on Apple Silicon produces arm64 images that Pods reject.
- **`LD_LIBRARY_PATH=''`** — set in every step's bash prelude. Required for the `nvidia/cuda:*` base + uv-installed torch (see upstream `docs/setup.md`).
- **`use_torch_compile=false`** — Inductor's auto-tuned kernels exceed sm_120 shared-memory limits on Blackwell. Re-enable on H100.
- **`/tmp` symlink to PVC** — `cosmos_framework.scripts.train` writes DCP checkpoints under `/tmp/imaginaire4-output` by convention; without the symlink they evaporate with the Pod. The `sft` and `sftMixed` step scripts handle this.
- **HF token** — gated `nvidia/*` Cosmos3 model repos may require a classic Read token in some environments. Fine-grained tokens silently 404 on gated repos. Get one from https://huggingface.co/settings/tokens.

## Status

Validated single-node on 8× RTX Pro 6000 Blackwell (sm_120, CUDA 12.8, FSDP across 8 GPUs). A multi-node H100 SXM variant with `cw-mpijob` orchestrating Cosmos3-Super (32B, LoRA-only SFT, 720p) over InfiniBand is in development.
