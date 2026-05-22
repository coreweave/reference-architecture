# Synthetic data generation prompts

Each `*.json` in this directory is one input sample for `cosmos3.scripts.inference`
in `forward_dynamics` or `policy` mode. The format matches the upstream
`inputs/omni/action_policy_robot.json` exactly — see that file for the
canonical reference.

The synthetic data Job (`demo/k8s/job-generate-synthetic.yaml`) globs
`/workspace/demo/prompts/synthetic/*.json` and emits one MP4 per input into
`/mnt/cosmos3/outputs/synthetic/`.

## Generating more prompts

For the recorded demo we want ~50-200 prompts to overfit-as-demo SFT against.
Hand-write one or two representative seeds in this directory, then expand
programmatically:

```python
# Run from the workbench Pod.
import json, pathlib, random
seed_path = pathlib.Path("/workspace/demo/prompts/synthetic/example_pick_and_place.json")
out_dir   = pathlib.Path("/workspace/demo/prompts/synthetic")
seed = json.loads(seed_path.read_text())

objects = ["red block", "blue cup", "yellow banana", "green apple", "wooden bowl"]
targets = ["left of the plate", "inside the bowl", "on the napkin", "next to the cup"]

for i in range(200):
    sample = dict(seed)
    sample["prompt"] = f"Put the {random.choice(objects)} {random.choice(targets)}. " \
                       "This video is captured from a first-person perspective looking at the scene."
    sample["seed"] = i
    (out_dir / f"synthetic_{i:04d}.json").write_text(json.dumps(sample, indent=2))
```
