# CoreWeave Fully Connected - SUNK Fine-Tuning Demo

QLoRA fine-tune of Qwen3.8-27B on `winglian/pirate-ultrachat-10k` (talk like a pirate) across 2 nodes x 8 B200 GPUs (16 total) with Axolotl + DDP (torchrun), scheduled by SUNK (Slurm on Kubernetes). The SUNK cluster is installed onto an existing Kubernetes cluster from this repo with Kustomize + Helm.

Flow:
1. `k8s/` - install cert-manager, the SUNK operator, and the Slurm cluster
2. `uv.sbatch` - sync the Python env on a compute node (shared filesystem)
3. `fine_tuning/run.sbatch` - train, merge the LoRA adapter, upload to CAIOS
4. `inference/inference_test.py` - test base vs adapter vs merged on one GPU

---

## Repository Layout

```
k8s/
  cert-manager/kustomization.yaml   # cert-manager chart + cert-issuers (SUNK prereq)
  sunk/                             # SUNK operator chart
  slurm/                            # the actual Slurm cluster definition
fine_tuning/
  run.sbatch                        # multi-node job: train -> rewrite adapter -> merge -> upload
  merge.py                          # merge adapter into a full bf16 model
  rewrite_adapter.py                # normalize adapter key names before merging
  upload.py                         # upload a directory to CAIOS (S3-compatible) with boto3
  configs/qwen/                     # per model axolotl recipes
inference/
  inference_test.py                 # compare base / adapter / merged generations on one GPU
uv.sbatch                           # `uv sync` as a Slurm job (builds env on a compute node)
```

---

## Prerequisites

- A Kubernetes cluster (CoreWeave CKS or similar) with a working `kubeconfig`
- `kubectl` + `kustomize` (builds use `--enable-helm` and pull charts from the CoreWeave Helm repos)
- Python deps are managed with [`uv`](https://docs.astral.sh/uv/). The env may not build locally depending on your environment, I recommend connecting your IDE to your sunk login pod.

---

## Adapting This to Your Cluster

Values below are hard-coded to my environment and must be changed before you run anything:

| File / input | What to change |
|---|---|
| kube context | point `kubectl` at the cluster you want to install onto |
| `k8s/slurm/slurm.yaml` | `scim_base_url` (replace `cw623e` with your CoreWeave org) |
| `fine_tuning/run.sbatch` | `JOB=` (which config in `fine_tuning/configs/qwen/` is used), `ENV_DIR=/mnt/data/fc-demo` if you clone somewhere else, `*CAIOS_*` env vars to piont to your bucket |
| `fine_tuning/configs/qwen/*.yaml` | `wandb_project`, and `wandb_entity` |
| W&B | jobs run with `wandb_mode: online`, so `WANDB_API_KEY` must be in the Slurm job environment, or switch the Axolotl config to offline |
| `inference/inference_test.py` | `MODEL` and the hard-coded `CHECKPOINT` (currently `3.8-27b-pirate-71`) |

The Slurm login flow also assumes your CoreWeave org account is in the `slurm-users` SCIM group and you have a public ssh key configured in your profile, otherwise you won't have a working shell user on the login node.

---

## 1. Install SUNK on Kubernetes

Apply in this order (each is a Kustomize overlay that renders Helm charts):

```bash
# 1. cert-manager (required by the SUNK operator webhooks)
kustomize build --enable-helm k8s/cert-manager/ | kubectl apply -f -

# 2. the SUNK operator
kustomize build --enable-helm k8s/sunk/ | kubectl apply -f -

# 3. secrets (SCIM auth for nsscache + the `tokens` env secret)
kubectl -n tenant-slurm create secret generic nsscache-scim-secret  --from-literal=nsscache-scim-auth-token=<SCIM_READ_TOKEN_FROM_CW_CONSOLE>

# 4. the Slurm cluster itself (slurm-supporting PVCs, scheduler, login, b200 compute nodeset)
kustomize build --enable-helm k8s/slurm/ | kubectl apply -f -
```

Everything Slurm-related runs in the `tenant-slurm` namespace; the operator runs in `sunk`. `k8s/slurm/slurm.yaml` configures:

| Component | Setting |
|---|---|
| Compute nodeset | `b200`: 2 replicas (`b200-8x` definition), auto-partitioned |
| Login node | 1 replica, public CoreWeave LoadBalancer, IPv4 only |
| Shared storage | `slurm-data` and `slurm-home` PVCs (`shared-vast`, 1Ti), mounted at `/mnt/data` and `/mnt/home` on compute |
| Containers in jobs | pyxis + enroot enabled |
| Auth | nsscache against the CoreWeave SCIM API (`slurm-users` / `slurm-sudo` groups) |

Wait for the login pod to come up
```bash
kubectl get pods -n tenant-slurm
```

## 2. SSH into the login node

User accounts come from your CoreWeave org via SCIM. SSH to the login node's LoadBalancer with your org username/ssh key:

```bash
ssh <CW_USERNAME>@sunk.<CW_ORG_ID>-<CW_CLUSTER_NAME>.coreweave.app
```

The login and compute images install `uv` and the AWS CLI at startup (the `s6` scripts in `slurm.yaml`).

## 3. Clone and sync the Python environment

`slurm-data` is mounted at `/mnt/data` on the login node and all compute nodes, so you only install once. `uv.sbatch` runs `uv sync` as a Slurm job so the wheels are built on a compute node (matching arch/CUDA):

```bash
cd /mnt/data
git clone git@github.com:MYanello/fc-demo.git
cd fc-demo
sbatch /mnt/data/fc-demo/uv.sbatch
squeue --me
```

Watch `logs/uv-<JOBID>.out` until it finishes.

## 4. Submit the fine-tuning job

Edit `fine_tuning/run.sbatch` (or the configs under `fine_tuning/configs/qwen/`) if you want a different model, dataset, or output path, then set your environment variables as needed:

```bash
export CAIOS_BUCKET=<your-bucket>
export CAIOS_PREFIX=<your-bucket-prefix>
export WANDB_API_KEY=<your-wandb-api-key>
export HF_API_KEY=<your-huggingface-token>
```

Then run the job:
```bash
sbatch /mnt/data/fc-demo/fine_tuning/run.sbatch
squeue --me
tail -f /mnt/data/fc-demo/fine_tuning/logs/qwen-<JOBID>.out
```

The job runs on 2 nodes x 8 B200s = 16 GPUs. Axolotl launches via `srun` + `torchrun` with a c10d rendezvous on the head node. Each GPU holds the full frozen 4-bit base model; only the LoRA adapter gradients are all-reduced, over InfiniBand (see the NCCL env vars in `run.sbatch`).

`run.sbatch` is one job for the whole pipeline. After training it runs:

1. `rewrite_adapter.py <output_dir>`: normalizes LoRA key names in `adapter_model.safetensors`
2. `merge.py <output_dir> <output_dir>-merged`: loads the base model in bf16 and merges the adapter
3. `upload.py`: uploads the merged model to CAIOS (`s3://$CAIOS_BUCKET/fine-tuned-models/<job>...`)

Per-job logs land in `fine_tuning/logs/` while metrics go to CoreWeave Mission Control and Weights & Biases.

## 5. Smoke-test the result

Single-GPU check that generates from the base model, the trained adapter, and the merged checkpoint:

```bash
srun --partition=b200 --gpus-per-node=1 python /mnt/data/fc-demo/inference/inference_test.py
```

Point `CHECKPOINT` at the top of `inference_test.py` at your run's output directory (e.g. `fine_tuning/outputs/qwen/3.8-27b-pirate-<JOBID>`). The script expects a sibling `<checkpoint>-merged` directory from step 4.
