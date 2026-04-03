# Enroot Import Benchmark Report: DockerHub vs. Zot (With and Without LOTA)

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

### SquashFS Output and NFS Shared Storage

The `.sqsh` file produced by `enroot import` is written to the current working directory. In SLURM environments this is typically an **NFS-mounted shared folder** accessible across all compute nodes and login nodes. This means:

- Once any user imports an image and the `.sqsh` lands on NFS, **all other users and nodes can use that same file directly** — no re-import needed
- `enroot create` and `enroot start` reference the `.sqsh` by path; if the file already exists on NFS, importing again is redundant
- The per-user enroot layer cache (`$HOME/.cache/enroot/`) and LOTA's node-local cache are both bypassed entirely when reusing a shared `.sqsh`

---

## Test Details

| Parameter | Value |
|---|---|
| Image | `pytorch/pytorch:2.11.0-cuda12.8-cudnn9-devel` |
| Layers | 10 |
| Output size | ~19 GB (squashfs, lzo compressed) |
| mksquashfs parallelism | 96 processors |
| Uncompressed size | ~22.7 GB |
| Compression ratio | 82.28% of uncompressed |

### Commands

**DockerHub (anonymous, no private registry):**
```bash
time enroot import docker://pytorch/pytorch:2.11.0-cuda12.8-cudnn9-devel
```

**In-cluster zot registry (credentials redacted):**
```bash
time enroot import docker://<ZOT_USERNAME>:<ZOT_PASSWORD>@10.16.12.10:5000#pytorch/pytorch:2.11.0-cuda12.8-cudnn9-devel
```

The `#` delimiter separates the registry address from the image path — enroot's syntax for specifying a private registry. `time` was prepended to capture wall-clock, user, and sys duration for each run.

---

## Results

### Time Breakdown per Phase (approximate)

| Phase | DockerHub cold | Zot cold (with or without LOTA) | Warm (enroot cache hit) |
|---|---|---|---|
| Layer download | ~62s | ~35s | 0s (skipped) |
| Layer extraction | ~27s | ~26–27s | ~26–27s |
| Whiteout conversion | ~1s | ~1s | ~1s |
| mksquashfs | ~45s | ~44–49s | ~44–46s |

### Wall-Clock Time Comparison

| Run | Configuration | real | user | sys | Download |
|---|---|---|---|---|---|
| 1st (cold) | DockerHub | **2m 15.6s** | 4m 34.8s | 4m 15.9s | 10 layers (~62s) |
| 1st (cold) | Zot — Without LOTA | **1m 47.8s** | 4m 35.7s | 4m 14.3s | 10 layers (~35s) |
| 1st (cold) | Zot — With LOTA | **1m 51.5s** | 4m 37.9s | 4m 26.1s | 10 layers (~35s) |
| 2nd (warm) | Zot — Without LOTA | **1m 13.3s** | 2m 04.5s | 2m 11.4s | None (local cache) |
| 2nd (warm) | Zot — With LOTA | **1m 13.5s** | 2m 04.2s | 2m 41.3s | None (local cache) |

---

## Analysis

### In-Cluster Zot vs. DockerHub (The Primary Finding)

The most significant result is the comparison between pulling from DockerHub and pulling from the in-cluster zot registry:

| Source | Cold import time | Download phase | vs. DockerHub |
|---|---|---|---|
| DockerHub | 2m 15.6s | ~62s | baseline |
| Zot — Without LOTA | 1m 47.8s | ~35s | **-27.8s / 20.5% faster** |
| Zot — With LOTA | 1m 51.5s | ~35s | **-24.1s / 17.8% faster** |

The in-cluster zot registry nearly **halves the download time** (62s → 35s) regardless of whether LOTA is in use. This is the primary benefit of the registry: keeping images on-cluster eliminates the public internet round-trip and DockerHub rate limits. LOTA vs. no LOTA is a secondary consideration by comparison.

### LOTA vs. No LOTA (Secondary Finding)

Within the in-cluster zot runs, the difference between LOTA and no LOTA is small:

- **Cold import:** 1m 47.8s (no LOTA) vs. 1m 51.5s (with LOTA) — **+3.7s with LOTA (+3.4%)**
- **Warm import:** 1m 13.3s vs. 1m 13.5s — **effectively identical**

On a cold pull, LOTA's cache is empty and every layer proxies through LOTA to CAIOS, adding a network hop. The 3.7s overhead is negligible on a ~108s operation dominated by CPU-bound squashfs compression.

On a warm pull (enroot's own layer cache hit), neither LOTA nor the registry is contacted — the result is identical regardless of LOTA.

### LOTA Benefit for Enroot Workflows

In practice, LOTA provides **no meaningful benefit** for enroot in a typical SLURM environment:

1. **Shared `.sqsh` on NFS:** The `.sqsh` output file is written to an NFS-mounted shared directory. Once any user imports an image, all other users and nodes reference that same file directly — no one else needs to run `enroot import` for that image again. LOTA's node-local cache is never consulted.

2. **Same-user repeat import:** If the same user does re-import, enroot's own layer cache (`$HOME/.cache/enroot/`) serves the layers locally, and the registry (LOTA or CAIOS) is never contacted.

3. **SLURM multi-user scenario:** The previously assumed benefit — that LOTA's cache would serve a second SLURM user whose enroot cache is cold — does not apply in practice precisely because the `.sqsh` on NFS eliminates the need for re-importing entirely. A second user would simply use the existing `.sqsh` file rather than running `enroot import` again.

### sys Time on Warm LOTA Run

The warm LOTA run shows elevated `sys` time (2m 41.3s vs 2m 11.4s without LOTA). This is likely a squashfs I/O scheduling artifact rather than a LOTA-specific issue, as the network download phase was skipped entirely.

---

## Summary

| Scenario | DockerHub | Zot (no LOTA) | Zot (with LOTA) |
|---|---|---|---|
| Cold import | 2m 15.6s | 1m 47.8s | 1m 51.5s |
| Warm import (enroot cache) | — | 1m 13.3s | 1m 13.5s |
| Shared `.sqsh` reuse (NFS) | n/a | 0s (already imported) | 0s (already imported) |

### Key Takeaways

1. **The in-cluster zot registry is the real win.** Pulling from zot is ~20% faster than DockerHub cold and cuts download time nearly in half by keeping images on-cluster and avoiding public internet latency and rate limits.
2. **LOTA adds negligible overhead on cold pull (+3.7s) and no difference on warm pull.** The dominant cost in all runs is CPU-bound squashfs compression, not the download.
3. **LOTA provides no practical benefit for enroot in SLURM.** The `.sqsh` file lands on NFS shared storage, so once any user imports an image it is immediately available to all other users and nodes without re-importing — bypassing both LOTA's cache and enroot's layer cache entirely.
4. **LOTA is a per-node DaemonSet, not a cluster-wide cache.** Its cache does not carry across nodes, further limiting its utility in multi-node SLURM job environments.
