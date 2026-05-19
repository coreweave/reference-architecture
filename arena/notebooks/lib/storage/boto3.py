import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from boto3.s3.transfer import TransferConfig

from .object_storage import ObjectStorage


def run_s3_upload_test(
    storage: ObjectStorage,
    bucket_name: str,
    test_file_size_gb: int = 1,
    multipart_threshold_mb: int = 8,
    multipart_chunksize_mb: int = 8,
    file_count: int = 1,
):
    """Run an S3 upload bandwidth test using boto3.

    Creates {file_count} test files of specified size (if it doesn't exist) and uploads it to
    the specified S3 bucket, measuring bandwidth and performance metrics.

    Args:
        storage (ObjectStorage): ObjectStorage client with configured S3 credentials.
        bucket_name (str): Target S3 bucket name.
        test_file_size_gb (int, optional): Size of test file in GB. Defaults to 1.
        multipart_threshold_mb (int, optional): File size threshold for multipart upload in MB.
            Defaults to 8.
        multipart_chunksize_mb (int, optional): Size of each multipart chunk in MB. Defaults to 8.
        max_concurrency (int, optional): Maximum number of concurrent threads. Defaults to 300.
        file_count (int, optional): Number of files to upload

    Returns:
        dict: Results dictionary containing:
            - success (bool): True if upload succeeded
            - file_key (str): S3 object key where file was uploaded
            - total_gb (float): Total file size in GB
            - elapsed (float): Upload time in seconds
            - bandwidth_mbs (float): Bandwidth in MB/s
            - bandwidth_gbps (float): Bandwidth in Gbps
            Or on failure:
            - success (bool): False
            - error (str): Error message

    Note:
        Test files are stored in /tmp/bandwidth-test and reused if they already exist.
    """
    test_dir = "/tmp/bandwidth-test"
    test_filename = f"{test_file_size_gb}GB"
    os.makedirs(test_dir, exist_ok=True)
    file_size_bytes = int(test_file_size_gb * 1024 * 1024 * 1024)
    test_file = f"{test_dir}/{test_filename}"

    if not os.path.exists(test_file):
        chunk_size = 64 * 1024 * 1024  # 64 MB
        zero_chunk = b"\0" * chunk_size
        with open(test_file, "wb") as f:
            remaining = file_size_bytes
            while remaining > 0:
                write_size = min(chunk_size, remaining)
                f.write(zero_chunk[:write_size])
                remaining -= write_size

    transfer_config = TransferConfig(
        multipart_threshold=multipart_threshold_mb * 1024 * 1024,
        multipart_chunksize=multipart_chunksize_mb * 1024 * 1024,
        max_concurrency=20,
        use_threads=True,
    )
    file_key = f"benchmark/{test_file_size_gb}GB"

    start = time.time()
    try:
        for i in range(file_count):
            storage.s3_client.upload_file(test_file, bucket_name, f"{file_key}_{i}", Config=transfer_config)
        elapsed = time.time() - start

        total_bytes = os.path.getsize(test_file) * file_count
        total_gb = total_bytes / (1024 * 1024 * 1024)
        size_mb = total_bytes / (1024 * 1024)
        bandwidth_mbs = size_mb / elapsed
        bandwidth_gbps = (total_bytes * 8) / elapsed / 1_000_000_000

        return {
            "success": True,
            "file_key": file_key,
            "total_gb": total_gb,
            "elapsed": elapsed,
            "bandwidth_mbs": bandwidth_mbs,
            "bandwidth_gbps": bandwidth_gbps,
        }

    except Exception as e:
        print(f"Upload failed: {e}")
        return {"success": False, "error": str(e)}


def run_s3_download_test(
    storage: ObjectStorage, bucket_name: str, object_key: str, chunk_size_mb: int = 8, max_concurrency: int = 300
) -> dict:
    """Run an S3 download bandwidth test using boto3.

    Downloads a specified object from S3 to local storage, measuring bandwidth
    and performance metrics.

    Args:
        storage (ObjectStorage): ObjectStorage client with configured S3 credentials.
        bucket_name (str): Source S3 bucket name.
        object_key (str): S3 object key to download.
        chunk_size_mb (int, optional): Size of each multipart chunk in MB. Defaults to 8.
        max_concurrency (int, optional): Maximum number of concurrent threads. Defaults to 300.

    Returns:
        dict: Results dictionary containing:
            - success (bool): True if download succeeded
            - object_key (str): S3 object key that was downloaded
            - output_path (str): Local path where file was saved
            - size_gb (float): File size in GB
            - elapsed (float): Download time in seconds
            - bandwidth_mbs (float): Bandwidth in MB/s
            - bandwidth_gbps (float): Bandwidth in Gbps
            Or on failure:
            - success (bool): False
            - error (str): Error message

    Note:
        Downloaded files are saved to /tmp/bandwidth-test directory.
    """
    if not bucket_name or not object_key:
        return {"success": False, "error": "bucket_name and object_key are required"}
    test_dir = "/tmp/bandwidth-test"
    os.makedirs(test_dir, exist_ok=True)

    # Extract filename from object_key for local storage
    filename = os.path.basename(object_key)
    output_path = f"{test_dir}/{filename}"
    try:
        head = storage.s3_client.head_object(Bucket=bucket_name, Key=object_key)
    except Exception as e:
        return {"success": False, "error": str(e)}
    total_bytes = head["ContentLength"]

    chunk_size = chunk_size_mb * 1024 * 1024
    ranges = [(offset, min(offset + chunk_size - 1, total_bytes - 1)) for offset in range(0, total_bytes, chunk_size)]

    fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:

        def download_range(start_byte: int, end_byte: int) -> None:
            resp = storage.s3_client.get_object(
                Bucket=bucket_name,
                Key=object_key,
                Range=f"bytes={start_byte}-{end_byte}",
            )
            os.pwrite(fd, resp["Body"].read(), start_byte)

        start = time.time()
        with ThreadPoolExecutor(max_workers=max_concurrency) as ex:
            futures = [ex.submit(download_range, s, e) for s, e in ranges]
            for f in as_completed(futures):
                f.result()
        elapsed = time.time() - start
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        os.close(fd)

    size_gb = total_bytes / (1024 * 1024 * 1024)
    size_mb = total_bytes / (1024 * 1024)
    bandwidth_mbs = size_mb / elapsed
    bandwidth_gbps = (total_bytes * 8) / elapsed / 1_000_000_000

    return {
        "success": True,
        "object_key": object_key,
        "output_path": output_path,
        "size_gb": size_gb,
        "elapsed": elapsed,
        "bandwidth_mbs": bandwidth_mbs,
        "bandwidth_gbps": bandwidth_gbps,
    }
