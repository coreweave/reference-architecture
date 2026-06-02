# Tutorial: Build a Cosmos3 Data Flywheel on CoreWeave

By the end of this tutorial you will have:

- A working **NVIDIA Cosmos3** world-foundation model running on a **CoreWeave Kubernetes** cluster
- Generated your own **synthetic robotics-manipulation video clips** using the base model
- **Fine-tuned** (SFT) the model on a mix of public data + your synthetic clips
- **Quantitatively measured** the improvement (we got Action MSE −88% on a 100-iter run)
- A **live HTTP endpoint** serving the fine-tuned model

**Time:** ~4 hours of attended work + ~2 hours of wall-clock waiting (1× 8-GPU node).
**You should be comfortable with:** `kubectl`, `helm`, Docker. No prior Cosmos3 knowledge required.

---

## Part 1 — Concepts (5 minutes of reading)

### What is Cosmos3?

A world-foundation model from NVIDIA: a **Reasoner** (vision-language model, Qwen3-VL backbone) and a **Generator** (diffusion video model) sharing latent representations. The same checkpoint handles text→image, text→video, image→video, forward/inverse dynamics, and action prediction — you pick the mode at inference time via JSON, not by swapping models.

For this tutorial we use **Cosmos3-Nano** (the 8B variant, fits a single 8-GPU node).

### What's a "data flywheel"?

The shorthand for the loop:

```
base model
   │
   ▼
generate synthetic clips
   │
   ▼
mix with real data
   │
   ▼
fine-tune (SFT)
   │
   ▼
better model ──► back to top
```

Each turn of the flywheel improves the model on the target domain. You'll run **one full turn** in this tutorial.

### Why does this matter for robotics?

Real robot trajectories are expensive to collect (hardware, time, supervised labels). A world model that's been fine-tuned on a domain can act as a **data amplifier** — generate large amounts of plausible synthetic experience, then condition policy training on it. Closing the loop with real-world rollouts is the long-term play; this tutorial demonstrates the synthetic-data step.

---

## Part 2 — Prerequisites (10 minutes)

Tick these off before you start:

- [ ] **CoreWeave Kubernetes cluster** with admin on a namespace. This tutorial uses `<your-namespace>` everywhere; substitute your own.
- [ ] **8× GPU node available** in that cluster. RTX Pro 6000 Blackwell (sm_120), H100, or equivalent. 80GB+ HBM per GPU.
- [ ] **VAST CSI** as the storage class (CoreWeave default is `shared-vast`).
- [ ] **CLI tools** installed locally: `kubectl` (matching your cluster), `helm ≥3.10`, `docker` with `buildx`, `gh` (optional, for PRs).
- [ ] **Hugging Face token** with read access to the public [`nvidia/Cosmos3-Nano`](https://huggingface.co/nvidia/Cosmos3-Nano) model and `Qwen/Qwen3-VL-8B-Instruct`. A classic "Read" token works; fine-grained tokens can silently 404 on gated repos.
- [ ] **Docker Hub** account (or any container registry your cluster can pull from).
- [ ] **15 minutes of attention** for the active steps. Long-running steps run unattended.

Quick verify:

```bash
kubectl version --short
helm version --short
docker buildx version
```

---

## Part 3 — One-time setup (15 minutes)

### Step 1: Set your shell variables

```bash
export KUBECONFIG=/path/to/your/CWKubeconfig
export NS=<your-namespace>
export REGISTRY=<your-registry>            # e.g. docker.io/<your-org> or ghcr.io/<your-org>
export HF_TOKEN=<your-hf-token>            # never commit this
```

**Verify your cluster:**

```bash
kubectl get nodes -L nvidia.com/gpu.product
```

You should see at least one node with a GPU label like `NVIDIA-H100-80GB-HBM3` or `NVIDIA-RTX-PRO-6000-Blackwell`.

### Step 2: Create the HF token Secret

```bash
kubectl -n "$NS" create secret generic hf-token \
  --from-literal=HF_TOKEN="$HF_TOKEN"
```

**How you know it worked:**
```bash
kubectl -n "$NS" get secret hf-token
# NAME       TYPE     DATA   AGE
# hf-token   Opaque   1      5s
```

### Step 3: Build and push the demo image

The image is a single-stage build on top of `nvcr.io/nvidia/pytorch:25.06-py3` — NVIDIA's recommended NGC PyTorch base for cosmos-framework (`cosmos-framework/docs/setup.md` Quickstart path). Inside the Dockerfile we apt-install the system deps cosmos-framework needs, `uv sync --group=cu128-train`, install cosmos-framework editable, then layer the chart's demo assets on top — so `import cosmos_framework` works in Pods without bind-mounts.

The build context is a clone of `NVIDIA/cosmos-framework` with the chart's `demo/` assets staged into it:

```bash
# 1. Clone cosmos-framework (one-time)
git clone https://github.com/NVIDIA/cosmos-framework.git /tmp/cf-build

# 2. Stage the chart's demo assets as cosmos-framework/demo/
rsync -a physical-ai/cosmos3/{prompts,configs,scripts} /tmp/cf-build/demo/

# 3. One docker build (~15 min on amd64-native, longer via QEMU on Apple Silicon)
docker buildx build --platform linux/amd64 \
  -f physical-ai/cosmos3/Dockerfile \
  -t "$REGISTRY/cosmos3-demo:<tag>" --push \
  /tmp/cf-build
```

> **Why `--platform linux/amd64`?** CW nodes are amd64; a default `docker build` on Apple Silicon produces arm64 and Pods fail with `no match for platform in manifest`.
>
> **Why the 25.06 NGC tag, not 25.09?** 25.09 ships CUDA 13 and requires the `cu130-train` uv group; on x86_64 RTX Pro 6000 Blackwell (sm_120) we validate against `cu128-train`. 25.06 is the most recent NGC PyTorch tag on CUDA 12 lineage. Bump to 25.09 + cu130-train once you've validated against your specific Blackwell silicon.
>
> **NGC pull credentials?** `nvcr.io/nvidia/pytorch` images are publicly pullable, but the first `docker pull` from `nvcr.io` on a host requires accepting NVIDIA's NGC terms — see https://catalog.ngc.nvidia.com/orgs/nvidia/containers/pytorch. CKS nodes have this already configured.

**How you know it worked:**
```bash
docker manifest inspect "$REGISTRY/cosmos3-demo:<tag>" | grep architecture
# "architecture": "amd64",
```

### Step 4: Apply the chart prerequisites

```bash
cd /path/to/this/physical-ai/cosmos3
helm template . --set image="$REGISTRY/cosmos3-demo:0.9" \
  | kubectl -n "$NS" apply -f -
```

This applies the **PVC** (1Ti VAST RWX) and the **workbench Pod** (CPU only, for shell-into diagnostics).

**How you know it worked:**
```bash
kubectl -n "$NS" get pvc cosmos3-shared workbench-pod 2>&1 | head -5
# NAME             STATUS   ...
# cosmos3-shared   Bound    ...
# pod/workbench    Running
```

---

## Part 4 — Stage the models and data (30 minutes, mostly wait)

This part runs four Jobs back to back. You'll start each, then check on it.

> **Re-running tip:** Jobs are immutable. If you need to re-run one, `kubectl delete job cosmos3-<name>` first.

### Step 5: Prefetch the base model

```bash
helm template . --set image="$REGISTRY/cosmos3-demo:0.9" \
  --set steps.prefetch.enabled=true \
  | kubectl -n "$NS" apply -f -

kubectl -n "$NS" wait --for=condition=complete --timeout=30m job/cosmos3-prefetch
```

Pulls **Cosmos3-Nano (~46 GB)** + **Qwen3-VL-8B (~16 GB)** from Hugging Face onto the shared PVC. Uses the HF Xet protocol, so it runs ~10× faster than `huggingface-cli download` (about 40 seconds end-to-end on CW's network — your numbers may vary).

**While you wait:** glance at `kubectl -n "$NS" logs -f job/cosmos3-prefetch` to watch the progress bars.

**How you know it worked:**
```bash
kubectl -n "$NS" exec workbench -- du -sh /mnt/cosmos3/hf_cache/hub/*
# ~46G  models--nvidia--Cosmos3-Nano
# ~16G  models--Qwen--Qwen3-VL-8B-Instruct
```

### Step 6: Convert HF → DCP format

```bash
helm template . --set image="$REGISTRY/cosmos3-demo:0.9" \
  --set steps.convert.enabled=true \
  | kubectl -n "$NS" apply -f -

kubectl -n "$NS" wait --for=condition=complete --timeout=30m job/cosmos3-convert
```

DCP (Distributed Checkpoint) is the on-disk format `cosmos_framework.scripts.train` expects. ~2 min on 1 GPU.

### Step 7: Run a smoke inference — see your first generated video

```bash
helm template . --set image="$REGISTRY/cosmos3-demo:0.9" \
  --set steps.smoke.enabled=true \
  | kubectl -n "$NS" apply -f -

kubectl -n "$NS" wait --for=condition=complete --timeout=30m job/cosmos3-smoke
```

This generates a single text-to-video clip from `inputs/omni/t2v.json` (prompt: a retail fruit-picking scene). ~13 min on 1 GPU.

**View the result:**
```bash
kubectl -n "$NS" cp workbench:/mnt/cosmos3/outputs/smoke/t2v/vision.mp4 smoke.mp4
open smoke.mp4
```

You should see a 5-second 480p video. This is your sanity check that the full inference chain works before you spend hours on SFT.

### Step 8: Download the bridge-v2 captioned dataset

```bash
helm template . --set image="$REGISTRY/cosmos3-demo:0.9" \
  --set steps.bridge.enabled=true \
  | kubectl -n "$NS" apply -f -

kubectl -n "$NS" wait --for=condition=complete --timeout=30m job/cosmos3-bridge
```

Pulls **bridge-v2-subset-synthetic-captions** (1,222 text+video pairs of robot manipulation, ~4 GB) onto the PVC. This is the canonical dataset for the mixed-modality SFT experiment.

---

## Part 5 — Run the flywheel (2 hours, mostly wait)

### Step 9: Generate synthetic clips with the base model

```bash
helm template . --set image="$REGISTRY/cosmos3-demo:0.9" \
  --set steps.generateSynthetic.enabled=true \
  | kubectl -n "$NS" apply -f -

kubectl -n "$NS" wait --for=condition=complete --timeout=90m job/cosmos3-generate-synthetic
```

Expands one seed prompt (in `prompts/synthetic/example_pick_and_place.json`) into 16 variations using `prompts/expand.py`, then runs `cosmos_framework.scripts.inference` across 8 GPUs at 256p × 30 steps. ~60 min wall-clock.

**While you wait** is a good time to skim `prompts/expand.py` — it's a 70-line standalone script you can extend to thousands of prompts for a real production flywheel.

**How you know it worked:**
```bash
kubectl -n "$NS" exec workbench -- find /mnt/cosmos3/outputs/synthetic -name vision.mp4 | wc -l
# 16
```

### Step 10: Top up to 5% synthetic ratio

```bash
helm template . --set image="$REGISTRY/cosmos3-demo:0.9" \
  --set steps.sdgExtra.enabled=true \
  | kubectl -n "$NS" apply -f -

kubectl -n "$NS" wait --for=condition=complete --timeout=60m job/cosmos3-sdg-extra
```

Generates **48 more clips at 256p × 15 steps** so that the closed-loop dataset is exactly 5% synthetic (64 synthetic / (1222 bridge-v2 + 64) ≈ 5.0%). Matches bridge-v2's 256×256 resolution so the mixed dataset is resolution-consistent.

### Step 11: Assemble the closed-loop JSONL

This one runs from the workbench Pod (no Job needed; it's a few seconds of Python):

```bash
kubectl -n "$NS" exec workbench -- python /workspace/demo/scripts/build_closed_loop_jsonl.py
```

Reads bridge-v2's existing JSONL + your 64 synthetic clips' metadata, rewrites paths to be absolute, and emits a single `train/video_dataset_file.jsonl` at `/mnt/cosmos3/datasets/closed_loop/`.

**How you know it worked:**
```bash
kubectl -n "$NS" exec workbench -- wc -l /mnt/cosmos3/datasets/closed_loop/train/video_dataset_file.jsonl
# 1286
```

### Step 12: Run the smoke SFT (dry-run validation)

```bash
helm template . --set image="$REGISTRY/cosmos3-demo:0.9" \
  --set steps.sftSmoke.enabled=true \
  | kubectl -n "$NS" apply -f -

kubectl -n "$NS" wait --for=condition=complete --timeout=30m job/cosmos3-sft-smoke
```

Runs `cosmos_framework.scripts.train --sft-toml=…` with `trainer.max_iter=2` to validate FSDP wiring, dataloader, optimizer, and checkpoint-load chain. ~5 min. **Always run this before the real SFT** — it catches misconfig in minutes instead of hours.

**How you know it worked:** the Job completes (`Succeeded`) and the logs end with `--dry-run complete`.

### Step 13: Run the real SFT

Pick one of the two — they train different surfaces:

**Action-policy SFT** (faster, ~60 min, demonstrates measurable improvement on action prediction):

```bash
helm template . --set image="$REGISTRY/cosmos3-demo:0.9" \
  --set steps.sft.enabled=true \
  | kubectl -n "$NS" apply -f -

kubectl -n "$NS" wait --for=condition=complete --timeout=2h job/cosmos3-sft
```

**Mixed-modality SFT** (slower, ~8–10 h, trains the diffusion expert — pixels change visibly):

```bash
helm template . --set image="$REGISTRY/cosmos3-demo:0.9" \
  --set steps.sftMixed.enabled=true \
  | kubectl -n "$NS" apply -f -

kubectl -n "$NS" wait --for=condition=complete --timeout=12h job/cosmos3-sft-mixed
```

> **At this scale (100 / 1000 iter) the action SFT moves measurable metrics; the mixed SFT may not visibly shift the MP4s yet** — diffusion needs longer runs to flip pixels. For visibly different output, scale to the H100 multi-node variant.

---

## Part 6 — Evaluate, export, serve (1 hour)

### Step 14: Export the trained checkpoint

```bash
helm template . --set image="$REGISTRY/cosmos3-demo:0.9" \
  --set steps.export.enabled=true \
  | kubectl -n "$NS" apply -f -

kubectl -n "$NS" wait --for=condition=complete --timeout=30m job/cosmos3-export
```

Converts the DCP-format SFT output to HF safetensors at `/mnt/cosmos3/checkpoints/cosmos3-nano-sft-hf`, which is what `cosmos_framework.inference.ray.serve` will load.

### Step 15: Quantitative evaluation

```bash
helm template . --set image="$REGISTRY/cosmos3-demo:0.9" \
  --set steps.eval.enabled=true \
  | kubectl -n "$NS" apply -f -

kubectl -n "$NS" wait --for=condition=complete --timeout=2h job/cosmos3-eval
```

Runs `cosmos3.scripts.eval` against the LIBERO val split with both the base model and your SFT checkpoint. **This is your numerical proof of improvement.**

**Check the metrics:**
```bash
kubectl -n "$NS" exec workbench -- bash -c '
  echo "=== base ===";  cat /mnt/cosmos3/outputs/eval_base/metrics_aggregate.json
  echo "=== sft ==="; cat /mnt/cosmos3/outputs/eval_sft/metrics_aggregate.json
'
```

Expected on the action-policy SFT path (your numbers will vary):
```
=== base ===
  "action_mse_mean": 1.30,
  "psnr_mean": 18.75
=== sft ===
  "action_mse_mean": 0.15,   # -88%
  "psnr_mean": 18.69
```

### Step 16: Stand up Ray Serve

```bash
helm template . --set image="$REGISTRY/cosmos3-demo:<tag>" \
  --set rayServe.enabled=true \
  | kubectl -n "$NS" apply -f -

kubectl -n "$NS" wait --for=condition=available --timeout=30m deploy/cosmos3-serve
```

Cold start for Ray Serve is ~5–10 min (model load + Ray cluster init).

**Call the endpoint:**
```bash
kubectl -n "$NS" exec workbench -- python -c "
import httpx
r = httpx.post('http://cosmos3-serve:8000/generate',
  json={'name':'demo','model_mode':'text2video',
        'prompt':'<your structured multi-paragraph prompt>',
        'seed':0,'num_steps':35,'image_size':480,'fps':5},
  timeout=900)
print(r.status_code, r.json())
"
```

The endpoint speaks the same JSON shape `inputs/omni/t2v.json` uses — any client targeting the upstream Cosmos3 inference protocol works against this deployment unchanged.

---

## Part 7 — Recap and what's next

You just:

1. ✅ Built a `linux/amd64` container image with the cosmos3 source baked in
2. ✅ Provisioned shared storage and prereqs via a Helm chart (1 PVC + 1 Pod + 2 RBAC)
3. ✅ Pulled Cosmos3-Nano + Qwen3-VL backbone (~62 GB) onto the cluster
4. ✅ Generated 64 synthetic robot-manipulation clips using the base model
5. ✅ Merged them with bridge-v2 (1,286 total clips, 5% synthetic) and ran one turn of SFT
6. ✅ Quantitatively proved the fine-tune worked (Action MSE −88% in our run)
7. ✅ Exported the fine-tuned model and stood it up behind an HTTP endpoint
8. ✅ Have a live notebook you can use to drive new prompts through the trained model

**Where to go next:**

- **Scale the SFT.** At 100–1000 iters the diffusion expert barely shifts. The multi-node H100 variant targets ~10,000 iters with `torch.compile` re-enabled and FSDP-32 across 4 nodes via `cw-mpijob` over InfiniBand.
- **Extend `prompts/expand.py`.** The seed file produces 16 variations from one prompt; bump the corpus to thousands by adding new (object, target, scene) tuples.
- **Wire in real-world rollouts.** Replace bridge-v2 with your own robot trajectories. The JSONL format is documented in upstream `NVIDIA/cosmos-framework`'s `docs/training.md`.
- **Try Cosmos3-Super.** The 32B variant uses LoRA for SFT and trains at 720p. Single-node 8× H100 80GB fits with `data_parallel_shard_degree=4, context_parallel_shard_degree=2`. See the multi-node variant for the multi-node version.

**If something broke:**

- `kubectl -n "$NS" logs job/cosmos3-<step-name>` is your friend.
- The workbench Pod (`kubectl -n "$NS" exec -it workbench -- bash`) has the same image and can poke around the PVC interactively.
