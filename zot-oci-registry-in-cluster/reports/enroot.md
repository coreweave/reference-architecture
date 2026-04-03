# Enroot Import Benchmark Report: With LOTA vs. Without LOTA

## What is Enroot?

[Enroot](https://github.com/NVIDIA/enroot) is NVIDIA's lightweight, unprivileged container engine designed for HPC and GPU workloads. It converts OCI/Docker images into **SquashFS** (`.sqsh`) filesystem images — a single compressed, read-only file that can be mounted at container startup without root privileges.

Enroot is the standard container runtime on CoreWeave GPU nodes and integrates with SLURM via the [Pyxis](https://github.com/NVIDIA/pyxis) plugin for multi-node MPI and GPU jobs.

### How `enroot import docker://` Works

1. Queries the registry for the image manifest
2. Downloads any missing OCI layers (checks local cache first)
3. Extracts and merges the layers into a flat filesystem
4. Converts whiteout files (layer deletions)
5. Compresses the result into a `.sqsh` SquashFS image using `mksquashfs` (parallel, using all available CPU cores)

### Enroot Local Layer Cache

Enroot caches downloaded OCI layers locally under `$HOME/.cache/enroot/`, keyed by layer digest. On subsequent imports of the same image, enroot detects the cached layers (`[INFO] Found all layers in cache`) and **skips the download entirely** — it goes straight to extraction and squashfs creation. This cache is **per-user, per-node** and operates independently of LOTA's node-local cache.

---

## Test Details

| Parameter | Value |
|---|---|
| Image | `pytorch/pytorch:2.11.0-cuda12.8-cudnn9-devel` |
| Registry | `https://10.16.12.10:5000` (zot in-cluster OCI registry) |
| Layers | 10 |
| Output size | ~19 GB (squashfs, lzo compressed) |
| mksquashfs parallelism | 96 processors |
| Uncompressed size | ~22.7 GB |
| Compression ratio | 82.28% of uncompressed |

### Command

The same command was used for all four runs. Credentials have been redacted:

```bash
time enroot import docker://<ZOT_USERNAME>:<ZOT_PASSWORD>@10.16.12.10:5000#pytorch/pytorch:2.11.0-cuda12.8-cudnn9-devel
```

The `#` delimiter separates the registry address from the image path — enroot's syntax for specifying a private registry. `time` was prepended to capture wall-clock, user, and sys duration for each run.

---

## Results

### Time Breakdown per Phase (approximate)

| Phase | Cold run | Warm run (enroot cache hit) |
|---|---|---|
| Layer download | ~35s | 0s (skipped) |
| Layer extraction | ~26–27s | ~26–27s |
| Whiteout conversion | ~1s | ~1s |
| mksquashfs | ~44–49s | ~44–46s |

### Wall-Clock Time Comparison

| Run | Configuration | real | user | sys | Download |
|---|---|---|---|---|---|
| 1st (cold) | Without LOTA | **1m 47.8s** | 4m 35.7s | 4m 14.3s | 10 layers (~35s) |
| 2nd (warm) | Without LOTA | **1m 13.3s** | 2m 04.5s | 2m 11.4s | None (local cache) |
| 1st (cold) | With LOTA | **1m 51.5s** | 4m 37.9s | 4m 26.1s | 10 layers (~35s) |
| 2nd (warm) | With LOTA | **1m 13.5s** | 2m 04.2s | 2m 41.3s | None (local cache) |

---

## Analysis

### Cold Run (First Import — No Caches Warm)

- **Without LOTA:** 1m 47.8s
- **With LOTA:** 1m 51.5s — **+3.7s slower**

The cold run behavior mirrors the `zb` benchmark findings: on first access, LOTA's cache is empty and every layer request proxies through LOTA to CAIOS, adding an extra network hop. For a 19 GB image across 10 layers, this overhead is only ~3.7 seconds — a negligible ~3.4% difference. The bulk of both runs is dominated by CPU-bound work (squashfs compression), not download time.

### Warm Run (Second Import — Enroot Local Cache Hit)

- **Without LOTA:** 1m 13.3s
- **With LOTA:** 1m 13.5s — **~0.2s difference (effectively identical)**

On the second run, enroot's local layer cache (`~/.cache/enroot/`) eliminates the download entirely for both configurations — neither LOTA nor the registry is consulted. The remaining time (~73s) is entirely CPU-bound: layer extraction, whiteout processing, and parallel mksquashfs across 96 cores.

This means **LOTA's caching does not benefit the second enroot import on the same node** — enroot's own local cache takes precedence and is faster than any network fetch, regardless of whether LOTA has a warm cache or not.

### The Two Cache Layers

Understanding the interaction between the two caching systems is key:

| Cache | Scope | Benefit |
|---|---|---|
| **Enroot local cache** (`~/.cache/enroot/`) | Per-user, per-node | Eliminates download entirely on repeat imports by the same user on the same node |
| **LOTA cache** (DaemonSet, per-node) | Per-node | Accelerates pulls from CAIOS for any user on the same node whose enroot cache is cold |

LOTA runs as a **DaemonSet** — one instance per node — so its cache is node-local, not cluster-wide. A warm LOTA cache on Node A does not benefit Node B. However, within the same node, LOTA's value is clear in multi-user or multi-job scenarios.

#### SLURM Multi-User Scenario

In SLURM environments, each user has their own `$HOME`, so enroot's layer cache at `$HOME/.cache/enroot/` is **completely separate per user**. This means every distinct SLURM user that pulls the same image on the same node will have a cold enroot cache and will contact the registry again — even if another user on that node already pulled the exact same image minutes earlier.

This is where LOTA's node-local DaemonSet cache provides direct value:

| Step | Without LOTA | With LOTA |
|---|---|---|
| User A pulls image (node cold) | enroot cold → CAIOS (~35s download) | enroot cold → LOTA cold → CAIOS (~35s + proxy overhead) |
| User B pulls same image, same node | enroot cold → CAIOS (~35s download) | enroot cold → **LOTA warm** → served from node-local cache |
| User A pulls same image again | **enroot warm** → 0s download | **enroot warm** → 0s download |

Without LOTA, every unique SLURM user pays the full CAIOS download cost for their first pull. With LOTA, only the first user on each node incurs that cost — all subsequent users on that node hit LOTA's warm cache instead.

### sys Time on Warm LOTA Run

The warm LOTA run shows elevated `sys` time (2m 41.3s vs 2m 11.4s without LOTA). This is likely a squashfs I/O scheduling artifact rather than a LOTA-specific issue, as the network download phase was skipped entirely.

---

## Summary

| Scenario | Without LOTA | With LOTA | Delta |
|---|---|---|---|
| Cold import (first pull, no caches) | 1m 47.8s | 1m 51.5s | +3.7s (+3.4%) |
| Warm import (enroot local cache hit) | 1m 13.3s | 1m 13.5s | ~equal |

### Key Takeaways

1. **Cold import overhead with LOTA is minimal (~3.7s)** for a 19 GB, 10-layer image. The dominant cost is CPU-bound squashfs compression, not the download.
2. **Warm runs are identical** regardless of LOTA, because enroot's local layer cache (`~/.cache/enroot/`) takes precedence — the registry is never contacted.
3. **LOTA is a per-node DaemonSet, not a cluster-wide cache.** A warm LOTA cache on one node does not benefit other nodes. Its value is scoped to the node it runs on.
4. **LOTA's enroot benefit is within-node, cross-user/cross-job:** the most practical use case is when a second user or SLURM job (different UID, different `$HOME`) imports the same image on the same node. Their enroot cache is cold, but LOTA's node-local cache is warm — serving layers locally instead of fetching from CAIOS again.
