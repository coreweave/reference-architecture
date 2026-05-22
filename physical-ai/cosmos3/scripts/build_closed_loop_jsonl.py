# SPDX-FileCopyrightText: Copyright (c) 2026 CoreWeave. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Build /mnt/cosmos3/datasets/closed_loop/train/video_dataset_file.jsonl by
combining the public bridge-v2 corpus with cosmos3-generated synthetic clips
in the same bridge-v2 schema. All vision_path values become absolute so the
dataloader can resolve them regardless of working directory.

Run from the workbench Pod:
  python /workspace/demo/scripts/build_closed_loop_jsonl.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess


BRIDGE_TRAIN = pathlib.Path(
    "/mnt/cosmos3/datasets/bridge_v2/train/video_dataset_file.jsonl"
)
BRIDGE_VIDEO_ROOT = pathlib.Path("/mnt/cosmos3/datasets/bridge_v2/train")

# Each clip lives at <root>/synthetic_NNNN/vision.mp4 with a sample_args.json
# alongside containing the original prompt. The "_extra" round is the 64-clip
# 256p batch produced for the 5%-synthetic closed-loop training corpus.
SYNTHETIC_ROOTS = [
    pathlib.Path("/mnt/cosmos3/outputs/synthetic_extra"),
]

OUT_PATH = pathlib.Path(
    "/mnt/cosmos3/datasets/closed_loop/train/video_dataset_file.jsonl"
)


def probe(video: pathlib.Path) -> tuple[int, int, int, float]:
    """Return (width, height, nb_frames, duration_s) for an MP4."""
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=width,height,nb_frames",
            "-show_entries", "format=duration",
            "-of", "json", str(video),
        ],
        text=True,
    )
    d = json.loads(out)
    s = d["streams"][0]
    return int(s["width"]), int(s["height"]), int(s["nb_frames"]), float(d["format"]["duration"])


def synthetic_entry(clip_dir: pathlib.Path, idx: int) -> dict | None:
    """Build a bridge-v2-format JSONL entry from a synthetic clip directory."""
    video = clip_dir / "vision.mp4"
    args  = clip_dir / "sample_args.json"
    if not video.exists() or not args.exists():
        return None
    args_d = json.loads(args.read_text())
    caption = args_d.get("prompt") or ""
    if not caption:
        return None
    w, h, n_frames, duration = probe(video)
    return {
        "uuid": f"synthetic_{clip_dir.parent.name}_{idx:04d}",
        "duration": round(duration, 3),
        "width": w,
        "height": h,
        "vision_path": str(video.resolve()),
        "t2w_windows": [{
            "start_frame": 0,
            "end_frame":   max(0, n_frames - 1),
            "temporal_interval": 1,
            "caption":     caption,
        }],
    }


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    n_bridge = 0
    n_synth = 0
    with OUT_PATH.open("w") as out:
        # Bridge-v2 entries — rewrite relative vision_path to absolute.
        with BRIDGE_TRAIN.open() as br:
            for line in br:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if "vision_path" in row and not row["vision_path"].startswith("/"):
                    row["vision_path"] = str((BRIDGE_VIDEO_ROOT / row["vision_path"]).resolve())
                out.write(json.dumps(row) + "\n")
                n_bridge += 1
        # Synthetic entries.
        for root in SYNTHETIC_ROOTS:
            if not root.exists():
                continue
            for i, clip_dir in enumerate(sorted(d for d in root.iterdir() if d.is_dir())):
                entry = synthetic_entry(clip_dir, i)
                if entry is None:
                    continue
                out.write(json.dumps(entry) + "\n")
                n_synth += 1
    pct = (n_synth / (n_bridge + n_synth) * 100) if (n_bridge + n_synth) else 0
    print(f"bridge: {n_bridge}")
    print(f"synthetic: {n_synth}")
    print(f"synthetic ratio: {pct:.2f}%")
    print(f"output: {OUT_PATH}  ({OUT_PATH.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
