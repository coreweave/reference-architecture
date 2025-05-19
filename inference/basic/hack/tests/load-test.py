#!/usr/bin/env python3
"""
vllm_load_test.py - Load-test a vLLM (OpenAI-compatible) endpoint.

Features
========
* **Variable concurrency phases** - keep the requested number of in-flight requests topped-up until each phase completes.
* **Prompt file support** - supply `--prompts-file` with one prompt per line; a random one is chosen per request for realistic load-mix.  Falls back to a single `--prompt` string.
* **Collects** success/fail counts, median/p95 latency, requests-per-second, and tokens-per-second.
* **Exports** results to JSON when `--out` is given.

Example
-------
```bash
python load-test.py \
  --endpoint https://navs-vllm.cw2025-training.coreweave.app/v1 \
  --model deepseek-ai/DeepSeek-R1 \
  --prompts-file prompts.txt \
  --concurrency 128 64 32 16 \
  --requests 200 \
  --out results.json
```

Dependencies
------------
```
pip install httpx[http2]  # + uvloop (optional, Linux/macOS)
```
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from pathlib import Path
from typing import Dict, List

import httpx

# --------------------------------------------------------------------------- #
# Helper to perform a single request
# --------------------------------------------------------------------------- #


async def _request_one(
    client: httpx.AsyncClient,
    url: str,
    payload_base: Dict,
    prompt: str,
    stats: Dict,
) -> None:
    """Issue one /chat/completions call and record metrics in *stats*."""
    start = time.perf_counter()
    try:
        payload = payload_base | {
            "messages": [{"role": "user", "content": prompt}],
        }
        r = await client.post(url, json=payload)
        latency = time.perf_counter() - start
        stats["latencies"].append(latency)
        if r.status_code == 200:
            stats["success"] += 1
            stats["tokens"] += r.json().get("usage", {}).get("total_tokens", 0)
        else:
            print(f"Request failed with status {r.status_code}: {r.text}")
            stats["fail"] += 1
    except Exception:
        stats["fail"] += 1


# --------------------------------------------------------------------------- #
# One concurrency phase
# --------------------------------------------------------------------------- #


async def _run_phase(
    *,
    base_url: str,
    model: str,
    prompts: List[str],
    n_requests: int,
    concurrency: int,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> Dict:
    """Fire *n_requests* while maintaining ~*concurrency* in-flight at all times."""
    stats: Dict = {"latencies": [], "success": 0, "fail": 0, "tokens": 0}

    payload_base = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    sem = asyncio.Semaphore(concurrency)
    url = f"{base_url.rstrip('/')}/chat/completions"

    async with httpx.AsyncClient(timeout=timeout, http2=True) as client:

        async def _bounded_call():
            async with sem:
                prompt = random.choice(prompts)
                await _request_one(client, url, payload_base, prompt, stats)

        tasks = [asyncio.create_task(_bounded_call()) for _ in range(n_requests)]
        phase_start = time.perf_counter()
        await asyncio.gather(*tasks)
        phase_elapsed = time.perf_counter() - phase_start

    lat = stats["latencies"]
    median = statistics.median(lat) if lat else None
    p95 = statistics.quantiles(lat, n=20)[18] if len(lat) >= 20 else None
    rps = n_requests / phase_elapsed if phase_elapsed else 0
    tps = stats["tokens"] / phase_elapsed if phase_elapsed else 0

    return {
        "concurrency": concurrency,
        "requests": n_requests,
        "success": stats["success"],
        "fail": stats["fail"],
        "median_latency_s": round(median, 3) if median else None,
        "p95_latency_s": round(p95, 3) if p95 else None,
        "throughput_rps": round(rps, 2),
        "tokens_per_second": round(tps, 2),
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _read_prompts(path: Path) -> List[str]:
    lines = [
        ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    if not lines:
        raise ValueError(f"Prompt file {path} contained no usable lines.")
    return lines


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="vLLM load-test utility")
    ap.add_argument(
        "--endpoint", required=True, help="Base API URL (no trailing slash)"
    )
    ap.add_argument(
        "--model", default="deepseek-ai/DeepSeek-R1", help="Model name to call"
    )
    ap.add_argument(
        "--prompt", default="Hello", help="Prompt text if --prompts-file omitted"
    )
    ap.add_argument(
        "--prompts-file", help="File with one prompt per line; overrides --prompt"
    )
    ap.add_argument(
        "--temperature", type=float, default=0.0, help="Sampling temperature"
    )
    ap.add_argument(
        "--max-tokens", type=int, default=100000, help="max_tokens parameter"
    )
    ap.add_argument(
        "--requests", type=int, default=100, help="Total requests per phase"
    )
    ap.add_argument("--concurrency", type=int, nargs="+", default=[1, 2, 4, 8, 16, 32])
    ap.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    ap.add_argument("--out", help="If given, write JSON summary to this file")
    return ap.parse_args()


async def main() -> None:
    args = parse_args()

    try:
        import uvloop  # type: ignore

        uvloop.install()
    except ImportError:
        pass

    if args.prompts_file:
        prompts = _read_prompts(Path(args.prompts_file))
    else:
        prompts = [args.prompt]

    results = []
    for c in args.concurrency:
        print(f"\n▶ Concurrency {c} …", flush=True)
        res = await _run_phase(
            base_url=args.endpoint,
            model=args.model,
            prompts=prompts,
            n_requests=args.requests,
            concurrency=c,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
        )
        results.append(res)
        print(
            f" ↳ {res['success']}/{args.requests} ok | "
            f"median {res['median_latency_s']}s | p95 {res['p95_latency_s']}s | "
            f"{res['throughput_rps']} rps | {res['tokens_per_second']} tps",
            flush=True,
        )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fp:
            json.dump(results, fp, indent=2)
        print(f"\nWrote results to {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
