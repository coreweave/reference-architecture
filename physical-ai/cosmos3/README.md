# Cosmos3 Data Flywheel on CoreWeave

> **Want to jump in?** Read **[TUTORIAL.md](TUTORIAL.md)** — a step-by-step walkthrough of the whole pipeline.

Reference architecture for running **NVIDIA Cosmos3** (a world-foundation model for physical AI / robotics) on **CoreWeave Kubernetes Service**. Covers the full lifecycle:

**synthetic data generation → SFT fine-tuning → DCP→HF export → live serving via Ray Serve → interactive marimo notebook.**

Validated single-node on 8× RTX Pro 6000 Blackwell + VAST CSI. Pure CKS — no SUNK / Slurm, no KubeRay operator. Packaged as a small Helm chart so each pipeline step is a single `values.yaml` flag.

## Quantitative result from the validation run

| Metric | Base Cosmos3-Nano | After 100-iter action-policy SFT | Δ |
|---|---:|---:|---:|
| Action MSE | 1.30 | **0.15** | **−88%** |
| PSNR | 18.75 | 18.69 | flat (expected — diffusion expert needs longer runs) |

## What's in the box

```
physical-ai/cosmos3/
├── TUTORIAL.md                # ← start here: 16-step walkthrough
├── README.md                  # this file
├── UPSTREAM_BUGS.md           # 8 upstream patches we applied + PR candidates back to NVIDIA
├── Chart.yaml                 # Helm chart metadata
├── values.yaml                # one entry per pipeline step
├── templates/                 # 3 templates + _helpers.tpl
├── Dockerfile                 # demo image (extends upstream cosmos3, cu128-train)
├── configs/sft_demo.yaml      # reference Hydra override (informational)
├── prompts/                   # seed prompts + programmatic expander
├── scripts/                   # closed-loop JSONL builder
└── marimo/cosmos3_demo.py     # reactive notebook — calls Ray Serve /generate
```

The chart renders to ~27 K8s resources when every step is enabled. Default is a no-op: enable steps individually with `--set steps.<name>.enabled=true`, or use an overrides file.

## Pipeline at a glance

| Phase | Steps in `values.yaml` | What you get |
|---|---|---|
| **Setup** | `prerequisites` (always-on), build image | PVC + workbench Pod + RBAC + demo container |
| **Stage** | `prefetch`, `convert`, `bridge`, `libero` | Base model + datasets on the PVC |
| **Smoke** | `smoke` | One 5-second video confirms the inference chain works |
| **Flywheel** | `generateSynthetic`, `sdgExtra` | 64 synthetic clips that you'll mix with bridge-v2 |
| **Fine-tune** | `sftSmoke`, then `sft` and/or `sftMixed` | DCP-format checkpoint with measurable improvement |
| **Export + serve** | `export`, `exportMixed`, `eval`, `rayServe`, `marimo` | HF safetensors, eval metrics, live HTTP endpoint, notebook UI |
| **Compare** | `compare`, `compareMixed`, `compareInDist` | Qualitative side-by-side videos |

Full step list, GPU counts, wraps, and outputs are in **[TUTORIAL.md § Pipeline](TUTORIAL.md#part-4--stage-the-models-and-data-30-minutes-mostly-wait)**.

## Quick reference

```bash
# Render + apply prerequisites only
helm template physical-ai/cosmos3 | kubectl -n "$NS" apply -f -

# Enable one step
helm template physical-ai/cosmos3 --set steps.smoke.enabled=true \
  | kubectl -n "$NS" apply -f -

# Enable everything
helm template physical-ai/cosmos3 \
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
  --set steps.eval.enabled=true \
  --set steps.compare.enabled=true \
  | kubectl -n "$NS" apply -f -
```

## Important gotchas

These are wired into the chart already but worth knowing:

- **`--platform linux/amd64`** — CW nodes are amd64; default `docker build` on Apple Silicon produces arm64 images that Pods reject.
- **`LD_LIBRARY_PATH=''`** — set in every step's bash prelude. Required for the `nvidia/cuda:*` base + uv-installed torch (see upstream `docs/setup.md`).
- **`use_torch_compile=false`** — Inductor's auto-tuned kernels exceed sm_120 shared-memory limits on Blackwell. Re-enable on H100.
- **`/tmp` symlink to PVC** — `cosmos3.scripts.train` writes DCP checkpoints under `/tmp/imaginaire4-output` by convention; without the symlink they evaporate with the Pod. The `sft` and `sftMixed` step scripts handle this.
- **HF token gating** — gated `nvidia-cosmos-ea/*` repos require a classic Read token. Fine-grained tokens silently 404. Get one from https://huggingface.co/settings/tokens.

See **[UPSTREAM_BUGS.md](UPSTREAM_BUGS.md)** for the full list of upstream issues with file:line, repro, and the candidate fix for each.

## Status

Validated single-node on 8× RTX Pro 6000 Blackwell (sm_120, CUDA 12.8, FSDP across 8 GPUs). A multi-node H100 SXM variant with `cw-mpijob` orchestrating Cosmos3-Super (32B, LoRA-only SFT, 720p) over InfiniBand is in development.
