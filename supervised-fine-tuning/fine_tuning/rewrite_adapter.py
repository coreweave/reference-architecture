import argparse
from pathlib import Path

from safetensors.torch import load_file, save_file


def rewrite_adapter(checkpoint_dir: str, adapter_filename: str = "adapter_model.safetensors") -> None:
    checkpoint = Path(checkpoint_dir)
    src = checkpoint / adapter_filename
    backup = checkpoint / f"{adapter_filename}.orig"

    if not src.exists():
        raise FileNotFoundError(f"Adapter file not found: {src}")

    state = load_file(src)
    renamed = {}

    for key, tensor in state.items():
        key = key.replace(".lora_A.weight", ".lora_A.default.weight")
        key = key.replace(".lora_B.weight", ".lora_B.default.weight")
        key = key.replace(".model.model.language_model.", ".model.model.")
        renamed[key] = tensor

    if not backup.exists():
        src.rename(backup)

    save_file(renamed, src)

    print(f"{len(renamed)} keys rewritten and saved to {src}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rewrite adapter safetensors key names.")
    parser.add_argument(
        "checkpoint",
        type=str,
        help="Path to the adapter checkpoint directory.",
    )
    parser.add_argument(
        "--adapter-file",
        type=str,
        default="adapter_model.safetensors",
        help="Name of the adapter safetensors file (default: adapter_model.safetensors).",
    )
    args = parser.parse_args()

    rewrite_adapter(args.checkpoint, args.adapter_file)


if __name__ == "__main__":
    main()
