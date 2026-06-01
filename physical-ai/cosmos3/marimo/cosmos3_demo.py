# SPDX-FileCopyrightText: Copyright (c) 2026 CoreWeave. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Cosmos3 on CoreWeave — blog companion notebook.
#
# Companion to the "Robotics Data Flywheel on CoreWeave using NVIDIA Cosmos3"
# blog post. Walks through the full pipeline that the surrounding K8s manifests
# orchestrate, with live cells against a running cluster.
#
# Run as a notebook server:
#   marimo run demo/marimo/cosmos3_demo.py --host 0.0.0.0 --port 2718 --no-token
# Interactive editing:
#   marimo edit demo/marimo/cosmos3_demo.py

import marimo

__generated_with = "0.10.0"
app = marimo.App(width="medium", app_title="Cosmos3 on CoreWeave")


@app.cell(hide_code=True)
def __():
    import marimo as mo
    import os
    import json
    import pathlib
    import subprocess

    # Required env vars — when this notebook is launched by the Helm chart's
    # cosmos3-marimo Deployment, both are populated automatically. When
    # launched standalone (e.g. `marimo edit cosmos3_demo.py`), the user
    # must set them in the shell, or the cells that hit Ray Serve / kubectl
    # would silently no-op.
    SERVE_URL = os.environ.get("COSMOS3_SERVE_URL")
    NS = os.environ.get("COSMOS3_NS")
    SHARED = pathlib.Path(os.environ.get("COSMOS3_SHARED", "/mnt/cosmos3"))
    return SERVE_URL, SHARED, NS, mo, os, json, pathlib, subprocess


@app.cell(hide_code=True)
def __(NS, SERVE_URL, mo):
    # Fail loud at notebook open time if the env isn't set. Avoids surprising
    # 404s / unbound NS errors three cells down.
    missing = [k for k, v in (("COSMOS3_SERVE_URL", SERVE_URL), ("COSMOS3_NS", NS)) if not v]
    if missing:
        mo.stop(
            True,
            mo.md(
                f"### ⚠️  Missing env: `{', '.join(missing)}`\n\n"
                "This notebook needs the following set before launch:\n\n"
                "```bash\n"
                "export COSMOS3_SERVE_URL=http://cosmos3-serve.<your-namespace>.svc.cluster.local:8000\n"
                "export COSMOS3_NS=<your-namespace>\n"
                "```\n\n"
                "When run from the chart's `cosmos3-marimo` Deployment, both are populated automatically."
            ),
        )
    return


@app.cell(hide_code=True)
def __(mo):
    mo.md(
        r"""
        # Cosmos3 on CoreWeave
        ### A robotics data flywheel — synthetic generation, fine-tuning, and serving on a single platform

        ---

        **What you're about to see:**

        1. We provision Cosmos3 (NVIDIA's world foundation model) on **CoreWeave Kubernetes** — 8× RTX Pro 6000 Blackwell, one node.
        2. We use the **base model** to generate synthetic robotics manipulation clips.
        3. We **fine-tune** Cosmos3 on those clips (overfit-as-demo: hundreds of steps, not millions).
        4. We **serve** the fine-tuned model via Ray Serve as a real HTTP endpoint.
        5. We call that endpoint from this notebook with new prompts and watch it generate.

        Every component runs on CoreWeave. The repo is upstream `NVIDIA/cosmos-framework`,
        used unmodified. Demo orchestration adds a Helm chart and this notebook;
        no forks of NVIDIA code.

        > **Honest framing**: bulk synthetic data generation and SFT each take ~hour(s)
        > of GPU time and were run as separate Jobs before opening this notebook —
        > their outputs are on the shared VAST volume. Cells below either render
        > those pre-computed artifacts or make live calls to the running Ray Serve
        > endpoint.
        """
    )
    return


@app.cell(hide_code=True)
def __(mo):
    mo.md(r"## 1 · Cluster context")
    return


@app.cell
def __(NS, mo, subprocess):
    nodes = subprocess.run(
        ["kubectl", "-n", NS, "get", "nodes", "-L", "gpu.nvidia.com/model", "-o", "wide"],
        capture_output=True, text=True, check=False,
    )
    pods = subprocess.run(
        ["kubectl", "-n", NS, "get", "pods", "-o", "wide"],
        capture_output=True, text=True, check=False,
    )
    mo.vstack([
        mo.md("**Nodes** (live `kubectl get nodes`):"),
        mo.ui.code_editor(value=nodes.stdout or nodes.stderr, language="text", disabled=True),
        mo.md("**Workloads** in the namespace:"),
        mo.ui.code_editor(value=pods.stdout or pods.stderr, language="text", disabled=True),
    ])
    return nodes, pods


@app.cell(hide_code=True)
def __(mo):
    mo.md(
        r"""
        ## 2 · The base model

        **Cosmos3 is the world foundation model.** NVIDIA's Cosmos3 is a
        Mixture-of-Transformer (MoT) architecture purpose-built for *physical AI*
        — text-to-video, image-to-video, action-policy generation, and forward
        dynamics. It's the model we fine-tune and serve. The variant in this
        demo is **Cosmos3-Nano** (8B parameters), the smallest of the EA family,
        which fits comfortably on a single GPU node for both training and
        inference.

        **Qwen3-VL-8B-Instruct is the *Reasoner* tower** inside Cosmos3's
        two-tower design. Cosmos3 doesn't train a vision-language model from
        scratch — it bolts diffusion-based generation onto an existing
        open-weight VLM. Qwen3-VL handles "what does this prompt mean and what
        does this image show?"; Cosmos3's diffusion expert handles "now
        generate video frames consistent with that understanding." You can
        think of it as: Qwen reads, Cosmos3 paints, and the two towers share
        latent representations through MoT cross-attention. Both must be
        present on disk for inference or training to work.

        Everything lives on the shared VAST volume so every Pod sees the same
        files at the same paths:

        - `/mnt/cosmos3/pretrained/` — read-only inputs:
            - **`Qwen3-VL-8B-Instruct`** — the public Qwen backbone (the Reasoner)
        - `/mnt/cosmos3/checkpoints/` — Cosmos3 weights at different stages:
            - **`cosmos3-nano-dcp`** — the *base* Cosmos3-Nano, converted from
              Hugging Face safetensors into PyTorch's Distributed Checkpoint
              (DCP) format. This is what the training Job reads in.
            - **`cosmos3-nano-sft-hf`** — the fine-tuned checkpoint *we produced
              on this cluster*, exported back out to Hugging Face safetensors so
              the inference and serving entry points can consume it. This is the
              model behind every "live" cell below.
        """
    )
    return


@app.cell
def __(SHARED, mo):
    ckpts = sorted((SHARED / "checkpoints").glob("*")) if (SHARED / "checkpoints").exists() else []
    pretrained = sorted((SHARED / "pretrained").glob("*")) if (SHARED / "pretrained").exists() else []
    mo.md(
        f"**Pretrained**: {', '.join(p.name for p in pretrained) or '_(not staged yet)_'}\n\n"
        f"**Checkpoints**: {', '.join(p.name for p in ckpts) or '_(not staged yet)_'}"
    )
    return ckpts, pretrained


@app.cell(hide_code=True)
def __(mo):
    mo.md(
        r"""
        ## 3 · Synthetic data generation (SDG)

        **What is SDG, and why does it matter for robotics?**

        Training a robotics policy traditionally means collecting thousands of
        real-world demonstrations: teleoperating a physical robot through a
        task, recording cameras + joint trajectories, hoping the data covers
        enough variation. It is slow, expensive, and bounded by how many
        hours of hardware time you have.

        Synthetic data generation flips the problem. A *world foundation
        model* like Cosmos3 has learned the dynamics, lighting, contact, and
        affordances of a robot manipulating objects from massive video
        pre-training. You can prompt it with a target scenario and have it
        produce hours of physically-plausible, labeled, diverse demonstration
        data — at the cost of GPU compute, not robot hours. The synthetic
        clips are then captioned, packaged as a training dataset, and used to
        post-train a *specialized* model for your specific task.

        This is the upstroke of the data flywheel:

        > **prompts → world model → synthetic clips → captions → new training
        > data → fine-tuned model → better generations → better prompts...**

        Each turn of the loop gets cheaper and faster than the last because the
        bottleneck shifts from physical hardware to compute that CoreWeave can
        provision on-demand.

        **What ran in this notebook's SDG step.** We expanded a single seed
        prompt (`demo/prompts/synthetic/example_pick_and_place.json`) into
        16 (object, location) variations using `demo/prompts/expand.py`,
        then ran them through base Cosmos3-Nano in `model_mode: policy` on
        8 GPUs via `torchrun --parallelism-preset=throughput`. Each output
        is a synthetic manipulation episode (MP4 + action chunk) written
        to the shared volume — the kind of artifact that would normally
        take a teleop operator hours per sample.

        The **live "Generate" button** further down sends a fresh prompt to
        the running Ray Serve endpoint and renders the result inline.
        """
    )
    return


@app.cell
def __(SHARED, mo):
    # Hero clip — the original base-model text-to-video sample on the
    # canonical inputs/omni/t2v.json prompt (multi-paragraph descriptive
    # caption, 480p × 35 denoising steps). This is the prompt format
    # Cosmos3 was trained against; short generic prompts produce far
    # weaker output (a real foundation-model property, not a CW issue).
    hero = SHARED / "outputs" / "smoke" / "t2v" / "vision.mp4"
    if hero.exists():
        hero_block = mo.vstack([
            mo.md(
                "**A robotic produce-picking scene generated by base Cosmos3-Nano on CoreWeave.**  \n"
                "_480p × 35 denoising steps; the full multi-paragraph prompt is in_ "
                "`inputs/omni/t2v.json`. _Generated end-to-end on a single 8-GPU node._"
            ),
            mo.video(src=str(hero)),
        ])
    else:
        hero_block = mo.md("_(hero clip not yet generated — see demo/k8s/job-smoke-inference.yaml)_")
    hero_block
    return hero_block,


@app.cell
def __(mo):
    live_prompt = mo.ui.text_area(
        label="Prompt for the live single-sample generation:",
        value="Pick up the red block and place it to the left of the bowl. "
              "This video is captured from a first-person perspective looking at the scene.",
        rows=3,
    )
    live_seed = mo.ui.slider(label="Seed", start=0, stop=99, value=42, show_value=True)
    run_live_gen = mo.ui.run_button(label="Generate (live, ~2-3 min)")
    mo.vstack([live_prompt, live_seed, run_live_gen])
    return live_prompt, live_seed, run_live_gen


@app.cell
def __(SERVE_URL, live_prompt, live_seed, mo, run_live_gen):
    if not run_live_gen.value:
        result = mo.md("_(click the button to generate)_")
    else:
        import httpx as _httpx
        try:
            _r = _httpx.post(
                f"{SERVE_URL}/generate",
                json={
                    # `name` is required by the OmniSampleArgs schema even though
                    # cosmos3.scripts.inference's CLI populates it from the input
                    # filename. Without it, /generate returns 500 on validation.
                    "name": "live_t2v",
                    "model_mode": "text2video",
                    "prompt": live_prompt.value,
                    "seed": int(live_seed.value),
                    "num_steps": 15,
                    "image_size": 256,
                    "fps": 5,
                },
                timeout=600,
            )
            _r.raise_for_status()
            payload = _r.json()
            result = mo.vstack([
                mo.md(f"**Generated** in {payload.get('elapsed_s', '?')}s"),
                mo.video(src=payload["video_path"]),
            ])
        except Exception as e:
            result = mo.md(f"⚠️  Ray Serve call failed: `{e}`\n\nIs `cosmos3-serve` Deployment ready?")
    result
    return (result,)


@app.cell(hide_code=True)
def __(mo):
    mo.md(
        r"""
        ## 4 · Captions & SFT dataset

        Two `cosmos3.scripts.*` commands turn the synthetic clips into a training-ready JSONL:

        - `caption_from_video` — VLM-captions every clip.
        - `captions_to_sft_jsonl` — emits the SFT JSONL the trainer consumes.

        The dataset lands at `/mnt/cosmos3/datasets/sft_demo.jsonl`.
        """
    )
    return


@app.cell
def __(SHARED, mo):
    jsonl = SHARED / "datasets" / "sft_demo.jsonl"
    if jsonl.exists():
        sample_lines = jsonl.read_text().splitlines()[:3]
        preview = "\n".join(sample_lines)
        body = mo.ui.code_editor(value=preview, language="json", disabled=True)
        meta = mo.md(f"**{sum(1 for _ in jsonl.open())}** rows in `sft_demo.jsonl`")
    else:
        body = mo.md("_(dataset not assembled yet — `kubectl apply -f demo/k8s/job-caption.yaml`)_")
        meta = mo.md("")
    mo.vstack([meta, body])
    return jsonl, body, meta


@app.cell(hide_code=True)
def __(mo):
    mo.md(
        r"""
        ## 5 · Fine-tuning (the flywheel step)

        `torchrun --nproc-per-node=8 -m cosmos3.scripts.train experiment=action_policy_sft_nano ...`

        The full Hydra override list is at `demo/k8s/job-sft.yaml`. Key knobs:

        - `trainer.max_iter=100` — overfit-as-demo. A real run is 16,000+.
        - `checkpoint.load_path=/mnt/cosmos3/checkpoints/cosmos3-nano-dcp` — DCP-converted base.
        - 8× RTX Pro 6000 Blackwell, FSDP across the single node, ~hours wall-clock.

        Below is the **loss curve from the pre-baked run** (wandb offline export).
        """
    )
    return


@app.cell
def __(SHARED, mo):
    loss_csv = SHARED / "outputs" / "sft_demo_cw" / "wandb_loss.csv"
    if loss_csv.exists():
        import pandas as pd
        df = pd.read_csv(loss_csv)
        chart = mo.ui.altair_chart(
            df.plot.line(x="step", y="loss").get_figure() if hasattr(df, "plot") else df
        )
    else:
        chart = mo.md(
            "_(loss curve not exported yet — extract from `/mnt/cosmos3/outputs/sft_demo_cw/wandb/` "
            "after the SFT Job completes)_"
        )
    chart
    return (chart,)


@app.cell(hide_code=True)
def __(mo):
    mo.md(
        r"""
        ## 6 · Two ways to fine-tune Cosmos3 — and where the gains show up

        Cosmos3's Mixture-of-Transformer architecture has **two trainable surfaces**:
        the *Reasoner* tower (VLM + action-prediction heads, used when Cosmos3 is
        deployed as a robot policy) and the *Generator* tower (the diffusion expert
        that paints video frames, used when Cosmos3 is a synthetic data factory).
        We fine-tuned both during this demo:

        | Experiment | Trains | Production use case |
        |---|---|---|
        | **`action_policy_sft_nano`** | Action-prediction layers in the Reasoner tower | Cosmos3 as a robotic controller (predicts next 16 frames of robot actions) |
        | **`mixed_modality_sft_nano`** | Diffusion expert in the Generator tower | Cosmos3 as a synthetic-data factory (generates physics-aligned training video) |

        A realistic note on what fine-tuning at this scale looks like:
        the **action-policy** run (100 iters on LIBERO) produces a *dramatic*
        and measurable improvement in the model's robot-command outputs (see eval
        table below). The **mixed-modality** run (1000 iters on a 5%-synthetic +
        bridge-v2 corpus) moves the diffusion expert's weights, but visible
        video-quality deltas at this iteration count are subtle — production runs
        at 16,000+ iters are where pixel-level changes become unmistakable.
        The metrics, not the MP4s, are where the fine-tuning shows up.
        """
    )
    return


@app.cell(hide_code=True)
def __(mo):
    mo.md(
        r"""
        ### Quantitative eval — `cosmos3.scripts.eval` on the LIBERO val split

        Both action-policy fine-tuning (which targets robot-command prediction) and
        the base model were evaluated on the same 16 held-out LIBERO samples.
        Two metrics from `metrics_aggregate.json`:

        - **Action MSE** — mean squared error between the model's predicted action
          chunks and the ground-truth LIBERO demonstrations. Lower is better.
        - **PSNR** — peak signal-to-noise ratio between the model's reconstructed
          video and the ground-truth video. Higher is better.
        """
    )
    return


@app.cell
def __(SHARED, mo):
    import json as _json
    base_m = SHARED / "outputs" / "eval_base" / "metrics_aggregate.json"
    sft_m  = SHARED / "outputs" / "eval_sft"  / "metrics_aggregate.json"
    if base_m.exists() and sft_m.exists():
        b = _json.loads(base_m.read_text())["policy"]
        s = _json.loads(sft_m.read_text())["policy"]
        table = (
            "| Metric                | Base Cosmos3-Nano | Action-policy SFT | Delta |\n"
            "|---                    |---                |---                |---|\n"
            f"| **Action MSE ⬇**     | {b['action_mse']['mean']:.4f}        | {s['action_mse']['mean']:.4f}        | **{(s['action_mse']['mean']-b['action_mse']['mean'])/b['action_mse']['mean']*100:+.1f}%** |\n"
            f"| **PSNR (dB) ⬆**      | {b['psnr']['mean']:.2f}             | {s['psnr']['mean']:.2f}             | {s['psnr']['mean']-b['psnr']['mean']:+.2f} dB |\n"
            f"\n_n = {b['action_mse']['count']} held-out LIBERO samples_"
        )
        eval_table = mo.md(table)
    else:
        eval_table = mo.md("_(eval not run yet — `kubectl apply -f demo/k8s/job-eval.yaml`)_")
    eval_table
    return eval_table,


@app.cell(hide_code=True)
def __(mo):
    mo.md(
        r"""
        ## 7 · Interactive serving

        The fine-tuned checkpoint is served via Ray Serve as a real HTTP endpoint —
        the same `POST /generate` endpoint the upstream NVIDIA repo ships. The
        Deployment manifest is at `demo/k8s/deploy-serve.yaml`; the entry point is
        `python -m cosmos3.ray.serve` (defined at `cosmos3/ray/serve.py:273`).

        Type a new prompt below and watch the fine-tuned model respond.
        """
    )
    return


@app.cell
def __(mo):
    serve_prompt = mo.ui.text_area(
        label="Prompt:",
        value="Stack the blue cup on top of the yellow plate. First-person view.",
        rows=3,
    )
    serve_seed = mo.ui.slider(label="Seed", start=0, stop=99, value=7, show_value=True)
    serve_button = mo.ui.run_button(label="Send to Ray Serve")
    mo.vstack([serve_prompt, serve_seed, serve_button])
    return serve_prompt, serve_seed, serve_button


@app.cell
def __(SERVE_URL, mo, serve_button, serve_prompt, serve_seed):
    if not serve_button.value:
        out = mo.md("_(click to send the prompt to the live endpoint)_")
    else:
        import httpx as _httpx
        import time as _time
        _t0 = _time.monotonic()
        try:
            _r = _httpx.post(
                f"{SERVE_URL}/generate",
                json={
                    "name": "live_interactive",
                    "model_mode": "text2video",
                    "prompt": serve_prompt.value,
                    "seed": int(serve_seed.value),
                    "num_steps": 15,
                    "image_size": 256,
                    "fps": 5,
                },
                timeout=600,
            )
            _r.raise_for_status()
            elapsed = _time.monotonic() - _t0
            out = mo.vstack([
                mo.md(f"Served from `{SERVE_URL}` in {elapsed:.1f}s"),
                mo.video(src=_r.json()["video_path"]),
            ])
        except Exception as e:
            out = mo.md(f"⚠️  Endpoint error: `{e}`")
    out
    return (out,)


@app.cell(hide_code=True)
def __(mo):
    mo.md(
        r"""
        ## Takeaways

        - Upstream NVIDIA `cosmos3` ran unmodified on **CoreWeave Kubernetes** — no forks, no patches.
        - A complete **data flywheel** — generate → caption → fine-tune → serve — fit inside a single
          CoreWeave tenant namespace with a VAST PVC and standard `nvidia.com/gpu` scheduling.
        - Serving uses the repo's native Ray Serve path. No KubeRay operator, no custom HTTP code —
          just `python -m cosmos3.ray.serve` inside a Deployment.
        - Same platform for synthetic data, training, and inference. One bill, one console, one
          security boundary.

        ---

        _Built on commit `$(git rev-parse --short HEAD)` of `NVIDIA/cosmos-framework`._
        """
    )
    return


if __name__ == "__main__":
    app.run()
