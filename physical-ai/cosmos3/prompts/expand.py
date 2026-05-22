# SPDX-FileCopyrightText: Copyright (c) 2026 CoreWeave. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Expand a single seed prompt JSON into many programmatic variations.

The synthetic-data generation Job consumes a glob of prompt files; this script
manufactures that corpus by varying (object, target_location) pairs against a
fixed seed JSON. Matches the README pattern at demo/prompts/synthetic/README.md.

Usage from the workbench Pod or any container with cosmos3 installed:
  python -m demo.prompts.expand \
    --seed   /workspace/demo/prompts/synthetic/example_pick_and_place.json \
    --output /tmp/prompts \
    --count  16
"""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib

OBJECTS = [
    "red block",
    "blue cup",
    "yellow banana",
    "green apple",
    "wooden bowl",
    "white mug",
    "silver spoon",
    "small cardboard box",
]
TARGETS = [
    "to the left of the plate",
    "inside the bowl",
    "on the napkin",
    "next to the cup",
    "in the center of the table",
    "behind the bottle",
    "in front of the user",
    "on top of the red mat",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", required=True, type=pathlib.Path,
                    help="Path to the seed JSON (e.g. example_pick_and_place.json).")
    ap.add_argument("--output", required=True, type=pathlib.Path,
                    help="Output directory to write synthetic_NNNN.json files.")
    ap.add_argument("--count", type=int, default=16,
                    help="Number of prompts to emit. Capped by len(OBJECTS) * len(TARGETS).")
    args = ap.parse_args()

    seed = json.loads(args.seed.read_text())
    args.output.mkdir(parents=True, exist_ok=True)

    pairs = list(itertools.product(OBJECTS, TARGETS))[: args.count]
    for i, (obj, tgt) in enumerate(pairs):
        sample = dict(seed)
        sample["prompt"] = (
            f"Pick up the {obj} and place it {tgt}. "
            "This video is captured from a first-person perspective looking at the scene."
        )
        sample["seed"] = i
        out = args.output / f"synthetic_{i:04d}.json"
        out.write_text(json.dumps(sample, indent=2))
        print(f"  wrote {out}")

    print(f"Done — {len(pairs)} prompts in {args.output}")


if __name__ == "__main__":
    main()
