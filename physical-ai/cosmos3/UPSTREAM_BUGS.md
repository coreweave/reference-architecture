# Upstream bugs discovered while building the CW demo

Running tally of bugs that surfaced while building this reference architecture on stock CKS. Each one is a candidate PR back to NVIDIA.

For each: **Repro**, **Symptom**, **Workaround applied here**, **Suggested upstream fix**.

> **Heads-up:** entries 1–8 were captured against the **EA codebase** (`nvidia-cosmos/cosmos3-ea-external`). On migration to the public `NVIDIA/cosmos-framework` release, the Python package was renamed `cosmos3` → `cosmos_framework` and several internal paths moved (e.g. `cosmos3/_src/imaginaire/utils/` → `cosmos_framework/utils/`). The symptoms below likely still reproduce, but **file:line and module paths may differ on the public release** — treat them as starting points and re-confirm against the current source before filing upstream PRs. Bug #9 from the EA catalog was already fixed upstream (`HF_VERSION` bumped from `1.13.0` to `1.16.4`) and has been removed.

---

## 1. Root `Dockerfile` is missing a bind-mount for `packages/`

**Files:** `Dockerfile:59-63`

**Repro:**
```bash
docker build --build-arg=CUDA_VERSION=12.8.1 -t cosmos3-base:cu128 .
```

**Symptom:**
```
error: Failed to generate package metadata for `diffusers-cosmos3==0.1.0 @ editable+packages/diffusers-cosmos3`
  Caused by: Distribution not found at: file:///workspace/packages/diffusers-cosmos3
```

**Root cause:** The `RUN uv sync ...` step uses BuildKit bind-mounts to expose `uv.lock`, `pyproject.toml`, and `.python-version` to the sandbox. `pyproject.toml:303` declares `diffusers-cosmos3 = { path = "packages/diffusers-cosmos3", editable = true }` — but `packages/` is never bind-mounted, so uv can't resolve it. Once a bind-mount for `packages/` is added, the editable build also needs `rw=true` because setuptools writes `.egg-info` into the source dir during install.

**Workaround applied** (this branch, `Dockerfile:60-65`):
```dockerfile
# CW demo: bind packages/ for editable diffusers-cosmos3 resolution; pending upstream PR.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=.python-version,target=.python-version \
    --mount=type=bind,source=packages,target=packages,rw \
    uv sync --locked --no-install-project --no-editable --all-extras --group=$(cat /root/.cuda-name)
```

**Suggested upstream fix:** Same one-line addition.

---

## 2. `docker/nightly.Dockerfile` has the same `packages/` bind-mount gap

**Files:** `docker/nightly.Dockerfile:50-52`

**Repro:** `docker build -f docker/nightly.Dockerfile .`

**Symptom:** Same `diffusers-cosmos3` resolution failure as bug #1, via `uv pip install -r pyproject.toml --all-extras` instead of `uv sync`.

**Workaround applied:** None — we don't use this Dockerfile for the CW demo (we use the root `Dockerfile`).

**Suggested upstream fix:** Add `--mount=type=bind,source=packages,target=packages,rw` to the same RUN block. Worth bundling into the same PR as bug #1.

---

## 3. Root `Dockerfile` produces an image without the cosmos3 source installed

**Files:** `Dockerfile:59-63` (uses `uv sync --no-install-project --no-editable`)

**Repro:** Build the root `Dockerfile`, run the container without bind-mounting the repo:
```bash
docker run --rm cosmos3-base:cu128 python -c "import cosmos3"
# ModuleNotFoundError: No module named 'cosmos3'
```

**Symptom:** `import cosmos3` fails. The repo's intended runtime is `docker run -v .:/workspace …` (per the `justfile` `_docker` recipe), which bind-mounts the host's source at runtime. That works for local dev but breaks any deployment surface that can't bind-mount (K8s Pods, ECS tasks, anything where the host filesystem isn't the repo).

**Root cause:** `--no-install-project` tells uv not to install the project itself; the image only contains cosmos3's *dependencies*. The justfile compensates by bind-mounting at runtime, but that's a documentation-only contract.

**Workaround applied** (`demo/Dockerfile`): a downstream image that copies the source in and installs editable:
```dockerfile
COPY pyproject.toml /workspace/pyproject.toml
COPY cosmos3/      /workspace/cosmos3/
COPY packages/     /workspace/packages/
COPY inputs/       /workspace/inputs/
RUN /workspace/.venv/bin/uv pip install --no-deps -e .
```

**Suggested upstream fix:** Either:
- Drop `--no-install-project` and add a `COPY cosmos3/ pyproject.toml /workspace/` step before `uv sync`, OR
- Keep the current `Dockerfile` as a "deps-only" base, but ship a second Dockerfile (e.g. `docker/runtime.Dockerfile`) that layers in the source for self-contained runs.

Either is fine — the current state where the only documented build target produces a non-self-contained image is the trap.

---

## 4. `prefetch_hf_checkpoints.py` aggregator fails for EA-only members

**Files:** `cosmos3/scripts/prefetch_hf_checkpoints.py:29-30`

**Repro:** With an HF token that has `nvidia-cosmos-ea` org access but NOT `nvidia/` access:
```bash
python -m cosmos3.scripts.prefetch_hf_checkpoints
```

**Symptom:**
```
Error: Model 'nvidia/Cosmos3-Experimental' not found.
If the repo is private, make sure you are authenticated and your token has the required permissions.
subprocess.CalledProcessError: Command '['uvx', 'hf@1.13.0', 'download', ...]' returned non-zero exit status 1.
```

**Root cause:** `prefetch_all()` iterates `itertools.chain(_CHECKPOINTS_EXPERIMENTAL.values(), _CHECKPOINTS_EA.values())` — EXPERIMENTAL first. The first item points at `nvidia/Cosmos3-Experimental` (or similar `nvidia/Cosmos3-*-Internal` repos at `cosmos3/args.py:632-661`), which EA members don't have access to. HF returns 404, script dies, EA repos never get tried.

The same module already has an `EARLY_ACCESS` flag (`cosmos3/args.py:680-682`) that gates which set ends up in `_CHECKPOINTS`. The prefetch aggregator just doesn't honor it.

**Workaround applied** (`demo/k8s/job-prefetch-checkpoints.yaml`): bypass the broken aggregator, call `_CHECKPOINTS_EA` directly:
```python
from cosmos3.common.checkpoints import register_checkpoints
register_checkpoints()
from cosmos3.args import _CHECKPOINTS_EA
for cfg in _CHECKPOINTS_EA.values():
    if "Nano" in cfg.hf.repository:
        cfg.hf.download()
```

**Suggested upstream fix:** Gate the EXPERIMENTAL loop on `EARLY_ACCESS`:
```python
from cosmos3._src.constants import EARLY_ACCESS  # or wherever it lives
checkpoints = _CHECKPOINTS_EA.values() if EARLY_ACCESS else itertools.chain(
    _CHECKPOINTS_EXPERIMENTAL.values(), _CHECKPOINTS_EA.values()
)
for cfg in checkpoints:
    cfg.hf.download()
```
Plus the same treatment for the `_DATASETS_EXPERIMENTAL` / `_DATASETS_EA` loop right after.

Alternatively, wrap each `cfg.hf.download()` in try/except-on-404 with a warning — more permissive but loses the loud failure on actual missing repos.

---

## 5. Root `Dockerfile` builds an image without training dependencies

**Files:** `Dockerfile:58` (the `sed -E 's/^([0-9]+)\.([0-9]+).*/cu\1\2/'` → produces `cu128`, not `cu128-train`)

**Repro:** Build the root `Dockerfile`, then run any training entry point:
```bash
torchrun --nproc_per_node=8 -m cosmos3.scripts.train \
  -o outputs/train --config-file cosmos3/configs/experiment/action_policy_sft_nano.yaml \
  --config-overrides "checkpoint.load_path=$DCP"
```

**Symptom:**
```
ModuleNotFoundError: No module named 'transformer_engine'
  at cosmos3/_src/vfm/utils/fused_adam.py:8
```
Surfaces only at actual optimizer init (line 8 of `fused_adam.py` does an unconditional top-level `import transformer_engine as te`). `--dry-run` skips this code path so it's a *runtime-only* failure.

**Root cause:** `pyproject.toml:208-213` shows that `transformer-engine`, `torchao`, and `triton` are exclusive to the `cu128-train` (and `cu130-train`) uv groups, but the Dockerfile's sed only produces `cu128`. The justfile compensates by running `just install` (which uses `cu128-train`) interactively inside the container at runtime — fine for `docker run -it`, broken for any K8s / batch deployment that doesn't have `just install` in its entrypoint.

**Workaround applied** (`Dockerfile:58-60` on this branch):
```diff
+# CW demo: -train suffix so transformer-engine + torchao + triton land in the
+# image (required by cosmos3/_src/vfm/utils/fused_adam.py for SFT). Pending upstream PR.
-RUN echo "$CUDA_VERSION" | sed -E 's/^([0-9]+)\.([0-9]+).*/cu\1\2/' > /root/.cuda-name
+RUN echo "$CUDA_VERSION" | sed -E 's/^([0-9]+)\.([0-9]+).*/cu\1\2-train/' > /root/.cuda-name
```

**Suggested upstream fix:** Either:
- Default the sed to `-train` (largest superset, ~few-hundred-MB image growth, makes the image work for both inference and training out of the box), OR
- Accept a `--build-arg=UV_GROUP_SUFFIX=-train` so callers opt in, OR
- Ship two Dockerfiles: `docker/inference.Dockerfile` and `docker/train.Dockerfile`.

Also worth wrapping `import transformer_engine` in `fused_adam.py` with a `try/except ImportError` and emitting a helpful error pointing at the right uv group, so users get an actionable message instead of a generic `ModuleNotFoundError`.

---

## 6. `cosmos3.scripts.train` writes checkpoints to `/tmp` regardless of `-o`

**Files:** `cosmos3/_src/imaginaire/...` (cluster output path resolution, hardcodes `/tmp/imaginaire4-output/`)

**Repro:**
```bash
torchrun --nproc_per_node=8 -m cosmos3.scripts.train \
  -o /mnt/persistent/sft_run \
  --config-file ... --config-overrides "checkpoint.save_iter=50"
# Training completes, "Done with training" prints, save_state_dict logs "SUCCESS"
ls /mnt/persistent/sft_run/
# config.yaml, console.log, debug.log, and a `job` SYMLINK to /tmp/...
ls /mnt/persistent/sft_run/job/checkpoints/
# ls: cannot access '...': No such file or directory  (because /tmp is gone)
```

**Symptom:** After training, the `-o` directory contains only `config.yaml`, `config_raw.yaml`, `console.log`, `debug.log` and a `job` symlink pointing at `/tmp/imaginaire4-output/<project>/<group>/<name>`. The actual DCP checkpoints (`checkpoints/iter_<N>/`) live under `/tmp/imaginaire4-output/` only.

**Root cause:** The default `job.cluster` config is `ClusterConfig` with empty `object_store_bucket_checkpoint` — meant for environments where checkpoints sync to an object store, or where `/tmp` is a persistent SSD on a long-lived VM. In any ephemeral-FS environment (K8s Pods, Slurm scratch, ECS tasks), `/tmp` evaporates at job end and the trained weights are silently lost. There's no error or warning — `console.log` proudly reports "Saved checkpoint to /tmp/...".

**Workaround applied** (`demo/k8s/job-sft.yaml`, in the bash before `torchrun`):
```bash
mkdir -p /mnt/cosmos3/imaginaire4-output
rm -rf /tmp/imaginaire4-output
ln -sfn /mnt/cosmos3/imaginaire4-output /tmp/imaginaire4-output
```
After this symlink, cosmos3 writes "to /tmp" but the bytes land on the VAST PVC.

**Cost:** We lost the first successful 100-iter SFT run to this. Had to re-train.

**Suggested upstream fix:** Either:
- Honor `-o` as the actual output base for checkpoints (not just logs). This is what users expect.
- OR loudly warn when `-o` and the cluster output path diverge, with a hint about the symlink workaround.
- OR document this prominently in `docs/training.md` (currently the doc says "iter_<iter>/: DCP checkpoints saved every ..." in the *output tree under -o*, which is wrong).

---

## 7. `cosmos3.ray.serve` binds HTTP proxy to 127.0.0.1, unreachable from a K8s Service

**Files:** `cosmos3/ray/serve.py:273`

**Repro:** Run the serve entry point inside any K8s Pod:
```bash
python -m cosmos3.ray.serve --parallelism-preset=latency -o /tmp/x --checkpoint-path Cosmos3-Nano
```
Then from any other Pod (or via a K8s Service): `curl http://<pod-ip>:8000/generate` → connection refused / TCP timeout.

**Symptom:** The serve log proudly reports:
```
INFO ... serve 1 -- Application 'cosmos3_omni' is ready at http://127.0.0.1:8000/.
```
The HTTP proxy is bound to localhost only. K8s Services (which route to the Pod's `podIP`, not localhost) can't reach it. From the kubelet's perspective, even a TCP readiness probe on port 8000 fails — nothing is listening on the external interface.

`RAY_SERVE_HTTP_HOST=0.0.0.0` environment variable is **not** honored in this Ray version (verified empirically — still binds 127.0.0.1).

**Root cause:** `ray.serve.run(router_app, name="cosmos3_omni", blocking=True)` is called without `http_options`. Ray Serve's default `HTTPOptions(host="127.0.0.1")` takes effect.

**Workaround applied** (`cosmos3/ray/serve.py:273` on this branch):
```diff
+    # CW demo: Ray Serve's HTTP proxy defaults to 127.0.0.1, making the endpoint
+    # unreachable from outside the Pod. Bind 0.0.0.0 so the K8s Service can route
+    # traffic in. Pending upstream PR.
+    ray.serve.start(http_options=ray.serve.config.HTTPOptions(host="0.0.0.0", port=8000))
     ray.serve.run(router_app, name="cosmos3_omni", blocking=True)
```

**Suggested upstream fix:** Either:
- Bind `0.0.0.0` by default — Ray Serve's localhost default is a security-conscious choice for laptops but the wrong default for the canonical "serve a foundation model" use case, which is essentially always behind a Service / load balancer.
- OR honor `RAY_SERVE_HTTP_HOST` (or a `--host` CLI flag wired through tyro) so users don't need a Python patch.

---

## Status as of last update

| # | Bug | Local workaround | Upstream PR |
|---|---|---|---|
| 1 | Root Dockerfile missing `packages/` bind | ✅ applied | pending |
| 2 | `docker/nightly.Dockerfile` same gap | n/a (not used) | pending (bundle with #1) |
| 3 | Root Dockerfile builds deps-only image (no cosmos3) | ✅ worked around in this directory's `Dockerfile` | pending |
| 4 | `prefetch_hf_checkpoints` aggregator ignores EA | ✅ worked around in `values.yaml` (`steps.prefetch`) | pending |
| 5 | Root Dockerfile uses `cu128` (no training deps) | ✅ applied | pending |
| 6 | `train.py` writes checkpoints to `/tmp` regardless of `-o` | ✅ symlink workaround in `values.yaml` (`steps.sft`) | pending |
| 7 | `cosmos3.ray.serve` binds 127.0.0.1, unreachable from K8s | ✅ applied | pending |
| 8 | `cosmos3.ray.serve` doesn't set Ray Serve `request_timeout_s` — 5-min default truncates inference | ✅ applied | pending (bundle with #7) |

---

## 8. `cosmos3.ray.serve` doesn't extend Ray Serve's request timeout

**Files:** `cosmos3/ray/serve.py:273` (the `ray.serve.start(...)` call patched in bug #7).

**Repro:** Send a generation request whose inference exceeds 300 seconds:
```bash
curl -X POST http://cosmos3-serve:8000/generate -d '{"name":"t","model_mode":"text2video","prompt":"...","seed":0,"num_steps":15,"image_size":256,"fps":5}'
```

**Symptom:** Client gets `HTTP 500 Internal Server Error` at exactly **300.1 seconds**; server logs show `asyncio.CancelledError` → `TimeoutError` → `POST /generate 500 300105.6ms`. The model worker is still happily sampling in the background — only the HTTP layer gave up.

**Root cause:** Ray Serve's `HTTPOptions(request_timeout_s=...)` defaults to 300s. Cosmos3 inference at sensible interactive quality (256p × 15 diffusion steps on a single replica) routinely exceeds that. The default is fine for sub-second JSON APIs; it's wrong for diffusion-model serving where requests are minutes-long by design.

**Workaround applied** (`cosmos3/ray/serve.py:273-276`, bundled with bug #7):
```python
ray.serve.start(http_options=ray.serve.config.HTTPOptions(
    host="0.0.0.0", port=8000, request_timeout_s=1800,
))
```
30-minute ceiling — comfortably covers even 480p × 35-step requests.

**Suggested upstream fix:** Set `request_timeout_s` to something like 1800 (or a config-driven value) in the `HTTPOptions` constructor. The current default exists for low-latency microservices, not for inference servers. Worth bundling with the 0.0.0.0 bind fix.

Add new entries to this file as we trip over them.
