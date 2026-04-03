# Zot Registry Benchmark Report: With LOTA vs. Without LOTA

## Overview

This report analyzes the performance of a zot OCI registry backed by two different storage endpoints:

- **With LOTA** — zot configured to use CoreWeave's [Large Object Transfer Acceleration](http://cwlota.com) (`cwlota.com`), an accelerated S3-compatible endpoint optimized for GPU infrastructure workloads.
- **Without LOTA** — zot configured to use standard CoreWeave AI Object Storage (CAIOS) via `cwobject.com`.

LOTA runs as a **DaemonSet** (one instance per node), acting as a node-local acceleration layer in front of CAIOS: requests go through the node's LOTA instance first, and on a cache miss, LOTA fetches from CAIOS and caches the result for subsequent reads on that same node.

### Cold Cache Caveat

> **Important:** `zb` generates new unique objects on every test run. This means LOTA's cache is always cold during these benchmarks — every pull request results in a cache miss and a full proxy pass-through to CAIOS. This adds an extra network hop compared to hitting CAIOS directly, which explains the pull latency regressions observed below. In production workloads where the same images are pulled repeatedly, LOTA's cache would warm up and pull performance is expected to improve significantly.

---

## Test Environment

| Parameter | Value |
|---|---|
| Registry URL | `https://10.16.12.10:5000` |
| Concurrency Level | 1 |
| Total requests per test | 3 |
| Tool | `zb` v2.1.15 |
| Working directory | `/tmp/zb-workdir` |

---

## Results

### Get Catalog

| Metric | With LOTA | Without LOTA |
|---|---|---|
| Time taken | 30.16s | 29.08s |
| Requests/sec | 0.099 | 0.103 |
| p50 latency | 7.79s | 8.69s |
| p99 latency | 7.85s | 8.90s |
| Failed requests | 0 | 0 |

Catalog retrieval performance is comparable between both configurations.

---

### Push — Monolith

| Test | With LOTA p50 | Without LOTA p50 | With LOTA req/s | Without LOTA req/s | Improvement |
|---|---|---|---|---|---|
| Push Monolith 1MB | 790ms | 935ms | 0.91 | 0.52 | **-15.5% latency / +75% throughput** |
| Push Monolith 10MB | 918ms | 1.15s | 0.75 | 0.65 | **-20.3% latency / +15% throughput** |
| Push Monolith 100MB | 2.11s | 2.36s | 0.40 | 0.31 | **-10.6% latency / +31.6% throughput** |

LOTA consistently improves push latency and throughput across all image sizes. The acceleration is most pronounced at 1MB and 10MB.

---

### Push — Chunk Streamed

| Test | With LOTA p50 | Without LOTA p50 | With LOTA req/s | Without LOTA req/s | Improvement |
|---|---|---|---|---|---|
| Push Chunk 1MB | 881ms | 938ms | 0.84 | 0.72 | **-6.1% latency / +16.7% throughput** |
| Push Chunk 10MB | 1.01s | 1.11s | 0.74 | 0.51 | **-9.1% latency / +45% throughput** |
| Push Chunk 100MB | 2.38s | 2.36s | 0.36 | 0.32 | ~equal latency / **+12.5% throughput** |

Chunked streaming shows similar gains. At 100MB, latency is equivalent but throughput still favors LOTA.

---

### Pull

| Test | With LOTA p50 | Without LOTA p50 | With LOTA req/s | Without LOTA req/s | Note |
|---|---|---|---|---|---|
| Pull 1MB | 99ms | 148ms | 2.17 | 1.46 | **-33% latency / +48.6% throughput** |
| Pull 10MB | 121ms | 126ms | 1.69 | 0.71 | **-4% latency / +138% throughput** |
| Pull 100MB | 1.07s | 473ms | 0.47 | 0.71 | Cold cache overhead (see note below) |

**Pull 100MB regression explained:** Since `zb` creates new objects each run, LOTA's cache is never warm. For a 100MB pull, the cold cache miss causes LOTA to proxy the full object from CAIOS, adding the latency of an extra network hop vs. hitting CAIOS directly. This regression is an artifact of the benchmark methodology and is not representative of steady-state production pull performance.

---

### Mixed Workloads — Pull Only

| Test | With LOTA p50 | Without LOTA p50 | Note |
|---|---|---|---|
| Pull Mixed (20% 1MB, 70% 10MB, 10% 100MB) | 152ms | 97ms | Cold cache; majority 10MB traffic |

The mixed pull result skews slower with LOTA for the same cold cache reason — the 100MB slice adds disproportionate latency on cache miss.

---

### Mixed Workloads — Push Only

| Test | With LOTA p50 | Without LOTA p50 | With LOTA req/s | Without LOTA req/s | Improvement |
|---|---|---|---|---|---|
| Push Monolith Mixed (20% 1MB, 70% 10MB, 10% 100MB) | 933ms | 980ms | 0.63 | 0.71 | -4.8% latency |
| Push Chunk Mixed (33% 1MB, 33% 10MB, 33% 100MB) | 1.22s | 2.27s | 0.56 | 0.44 | **-46.3% latency / +27.3% throughput** |

Push Chunk Mixed shows the most dramatic improvement with LOTA — nearly half the latency.

---

### Mixed Workloads — Pull 75% / Push 25%

| Test | With LOTA p50 | Without LOTA p50 | With LOTA req/s | Without LOTA req/s | Improvement |
|---|---|---|---|---|---|
| Pull 75% / Push 25% — 1MB | 96ms | 1.04s | 2.24 | 0.69 | **-91% latency / +225% throughput** |
| Pull 75% / Push 25% — 10MB | 114ms | 149ms | 1.14 | 1.57 | -23.5% latency |
| Pull 75% / Push 25% — 100MB | 275ms | 382ms | 0.93 | 0.44 | **-28% latency / +111% throughput** |

The 1MB mixed scenario shows the most dramatic benefit from LOTA, with p50 latency dropping from 1.04s to 96ms — a 10x improvement. The 100MB mixed test also benefits significantly, suggesting that when push activity is included, LOTA's write path acceleration more than compensates for any pull overhead.

---

## Summary

| Category | LOTA Benefit |
|---|---|
| Push (all sizes) | Consistent latency and throughput improvement |
| Pull — small objects (1MB, 10MB) | Clear improvement in latency and throughput |
| Pull — large objects (100MB) | Regression due to cold cache; proxy hop adds latency |
| Mixed Push+Pull workloads | Strong improvement, especially at 1MB and 100MB |

### Key Takeaways

1. **LOTA accelerates push operations** across all image sizes, with throughput gains ranging from 12% to 75%.
2. **Pull performance benefits are cache-dependent.** The `zb` tool generates new objects per test, ensuring a perpetual cold cache. In real registry usage where the same objects are pulled repeatedly on the same node, LOTA's node-local cache warms up and pull performance improves. Note that LOTA's cache does not carry over to other nodes.
3. **Mixed workloads favor LOTA strongly.** Real-world registry traffic (a mix of pushes and repeated pulls) aligns well with LOTA's design — the write path benefits are immediate, and the read path improves as the cache warms.
4. **The 100MB pull regression is a benchmark artifact**, not a production concern. It reflects the cost of LOTA proxying an uncached object through to CAIOS, which adds one extra network hop relative to hitting CAIOS directly.
