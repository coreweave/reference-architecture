import argparse
import os
from pathlib import Path

import boto3
from botocore.config import Config


def upload_to_caios(
    local_dir: Path,
    endpoint: str,
    bucket: str,
    prefix: str,
) -> str:
    prefix = prefix.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    remote_uri = f"s3://{bucket}/{prefix}"

    s3_config = Config(s3={"addressing_style": "virtual"})
    s3 = boto3.client("s3", endpoint_url=endpoint, config=s3_config)

    files = [p for p in local_dir.rglob("*") if p.is_file() and ".cache" not in p.relative_to(local_dir).parts]

    print(f"Uploading {len(files)} files to {remote_uri} from {local_dir}")
    for i, path in enumerate(files, start=1):
        rel_key = path.relative_to(local_dir).as_posix()
        key = f"{prefix}{rel_key}"
        s3.upload_file(str(path), bucket, key)

        if i % 100 == 0 or i == len(files):
            print(f"Uploaded {i}/{len(files)}")

    print(f"Upload complete: {remote_uri}")
    return remote_uri


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a directory to CAIOS")
    parser.add_argument("--local-dir", type=str, help="Path to the adapter checkpoint directory.")
    parser.add_argument(
        "--base-model",
        type=str,
        default=None,
        help="Base model name or path. Defaults to base_model_name_or_path in adapter_config.json.",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=os.getenv("CAIOS_ENDPOINT_URL", "http://cwlota.com"),
        help="CAIOS S3 endpoint URL.",
    )
    parser.add_argument(
        "--bucket",
        type=str,
        default=os.getenv("CAIOS_BUCKET", "myanello-fc"),
        help="CAIOS S3 bucket name.",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default=os.getenv("CAIOS_PREFIX", ""),
        help="S3 object prefix for the upload.",
    )
    args = parser.parse_args()

    upload_to_caios(
        local_dir=Path(args.local_dir),
        endpoint=args.endpoint,
        bucket=args.bucket,
        prefix=args.prefix,
    )


if __name__ == "__main__":
    main()
