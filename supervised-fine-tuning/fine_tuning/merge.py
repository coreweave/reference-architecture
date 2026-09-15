import argparse
import gc
import json
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def load_base_model_name(checkpoint: Path, base_model: str | None) -> str:
    if base_model is not None:
        return base_model

    adapter_config_path = checkpoint / "adapter_config.json"
    if adapter_config_path.exists():
        with open(adapter_config_path) as f:
            config = json.load(f)
        name = config.get("base_model_name_or_path")
        if isinstance(name, str) and name:
            return name

    raise ValueError(
        f"No base model specified and adapter_config.json not found or missing base_model_name_or_path in {checkpoint}"
    )


def merge(
    checkpoint: str,
    output: str | None,
    base_model: str | None,
) -> Path:
    checkpoint_path = Path(checkpoint)
    output_path = Path(output) if output else checkpoint_path.parent / f"{checkpoint_path.name}-merged"
    output_path.mkdir(parents=True, exist_ok=True)

    base_model_name = load_base_model_name(checkpoint_path, base_model)

    print(f"Loading base model: {base_model_name}")
    model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    print(f"Loading adapter: {checkpoint_path}")
    model = PeftModel.from_pretrained(model, str(checkpoint_path))

    print("Merging and unloading LoRA")
    model = model.merge_and_unload()

    print("Freeing memory before save")
    gc.collect()
    torch.cuda.empty_cache()

    print(f"Saving merged model to: {output_path}")
    model.save_pretrained(output_path, safe_serialization=True)

    print("Saving tokenizer")
    tokenizer = AutoTokenizer.from_pretrained(base_model_name, trust_remote_code=True)
    tokenizer.save_pretrained(output_path)

    print("Done.")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge a PEFT adapter into its base model.")
    parser.add_argument("checkpoint", type=str, help="Path to the adapter checkpoint directory.")
    parser.add_argument(
        "output",
        type=str,
        nargs="?",
        help="Output directory for the merged model. Defaults to <checkpoint>-merged.",
    )
    parser.add_argument(
        "--base-model",
        type=str,
        default=None,
        help="Base model name or path. Defaults to base_model_name_or_path in adapter_config.json.",
    )
    args = parser.parse_args()

    merge(args.checkpoint, args.output, args.base_model)


if __name__ == "__main__":
    main()
