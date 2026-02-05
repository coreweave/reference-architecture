#!/usr/bin/env python3
"""
Test bandwidth with downloads pinned to either CPU or GPU.

This simulates actual training where each GPU or CPU  on a node has its own data loader workers.

Usage:
python caios_lota_node_throughput_benchmark.py --gpu # GPU-pinned
python caios_lota_node_throughput_benchmark.py       # CPU-pinned (default)

Options:
  --gpu       Use GPU-pinned mode
  --cpu       Use CPU-pinned mode
  --help      Show help message and exit
"""

import os
import time
import uuid
import torch
import boto3
from boto3.s3.transfer import TransferConfig
from pathlib import Path
from multiprocessing import Process, Queue
import statistics

# Load credentials
# Set credentials in ~/.env
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')

if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
    raise ValueError("AWS credentials not found")

BUCKET = os.getenv('S3_BUCKET')
if not BUCKET:
    print("ERROR: S3_BUCKET not set. Please set S3_BUCKET=<orgid>-arena-benchmark in /mnt/data/env/.env", flush=True)
    exit(1)
S3_ENDPOINT = os.getenv('S3_ENDPOINT_URL', "https://cwobject.com")
PATH_PREFIX = ""  # Optional path prefix for shard files
NUM_SHARDS = 128  # Total shards available in bucket
LOTA_ENDPOINT = os.getenv('LOTA_ENDPOINT_URL', "http://cwlota.com")
# Write directly to /dev/null to avoid disk I/O overhead
OUTPUT_FILE = "/dev/null"


def ensure_bucket_exists():
    """Create the benchmark bucket if it doesn't exist."""
    region = os.getenv('AWS_DEFAULT_REGION')
    if not region:
        print("ERROR: AWS_DEFAULT_REGION not set", flush=True)
        exit(1)
    
    s3_client = boto3.client(
        's3',
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=region
    )
    
    try:
        s3_client.head_bucket(Bucket=BUCKET)
        print(f"Bucket '{BUCKET}' exists and accessible", flush=True)
        return
    except s3_client.exceptions.ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == '403':
            print(f"Bucket '{BUCKET}' exists but access denied. Check permissions.", flush=True)
            return
        elif error_code != '404':
            raise
    
    # Bucket doesn't exist, create it with region
    print(f"Creating bucket '{BUCKET}' in region '{region}'...", flush=True)
    try:
        s3_client.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={'LocationConstraint': region}
        )
        print(f"Bucket '{BUCKET}' created successfully", flush=True)
    except s3_client.exceptions.ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code in ('BucketAlreadyExists', 'BucketAlreadyOwnedByYou'):
            print(f"Bucket '{BUCKET}' already exists, continuing...", flush=True)
        else:
            print(f"Warning: Could not create bucket '{BUCKET}': {e}", flush=True)
            print("Please create the bucket manually if needed.", flush=True)


# Ensure bucket exists at module load
ensure_bucket_exists()
'''
   Shards are dummy test files with .dummy extension.
   Example listing:
   $ aws s3 ls --human-readable --endpoint-url https://cwobject.com cw-arena-benchmark/
    2025-11-21 21:17:42    2.5 GiB shard_000000.dummy
    2025-11-21 21:19:05    2.6 GiB shard_000001.dummy
    ...
'''

def download_on_gpu(worker_id, num_downloads, endpoint_url, multipart_config, result_queue):
    """Download shards with process pinned to specific GPU."""
    try:
        # Pin to specific GPU
        gpu_id = worker_id % torch.cuda.device_count()
        torch.cuda.set_device(gpu_id)
        
        # Also set CUDA_VISIBLE_DEVICES to restrict this process to one GPU
        import os
        os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu_id)
        
        # Configure transfer based on multipart_config
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/customizations/s3.html#boto3.s3.transfer.TransferConfig
        # Flavors of multipart config :- [concurrency, threshold, chunksize]
        # max_concurrency: number of concurrent chunks
        # multipart_threshold: minimum size of a chunk
        # multipart_chunksize: size of a chunk
        # use_threads: use threads to download chunks
        if multipart_config == '250mb':
            transfer_config = TransferConfig(
                max_concurrency=4,
                multipart_threshold=128 * 1024 * 1024,  # 128 MB
                multipart_chunksize=250 * 1024 * 1024,  # 250 MB chunks
                use_threads=True
            )
        elif multipart_config == '256mb':
            transfer_config = TransferConfig(
                max_concurrency=4,
                multipart_threshold=128 * 1024 * 1024,  # 128 MB
                multipart_chunksize=256 * 1024 * 1024,  # 256 MB chunks
                use_threads=True
            )
        elif multipart_config == '512mb':
            transfer_config = TransferConfig(
                max_concurrency=4,
                multipart_threshold=256 * 1024 * 1024,  # 256 MB
                multipart_chunksize=512 * 1024 * 1024,  # 512 MB chunks
                use_threads=True
            )
        elif multipart_config == '1024mb':
            transfer_config = TransferConfig(
                max_concurrency=4,
                multipart_threshold=512 * 1024 * 1024,  # 512 MB
                multipart_chunksize=1024 * 1024 * 1024,  # 1024 MB chunks
                use_threads=True
            )
        elif multipart_config == '2048mb':
            transfer_config = TransferConfig(
                max_concurrency=4,
                multipart_threshold=1024 * 1024 * 1024,  # 1024 MB
                multipart_chunksize=2048 * 1024 * 1024,  # 2048 MB chunks
                use_threads=True
            )
        else:
            transfer_config = None
        
        # Create S3 client
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )
        
        results = []
        total_bytes = 0
        
        start_time = time.time()
        
        for i in range(num_downloads):
            shard_idx = (worker_id * num_downloads + i) % NUM_SHARDS
            shard_key = f"{PATH_PREFIX}shard_{shard_idx:06d}.dummy"
            output_file = OUTPUT_FILE
            
            try:
                # Get file size from S3 metadata
                head_response = s3_client.head_object(Bucket=BUCKET, Key=shard_key)
                file_size = head_response['ContentLength']
                
                dl_start = time.time()
                
                if transfer_config:
                    s3_client.download_file(
                        BUCKET,
                        shard_key,
                        output_file,
                        Config=transfer_config
                    )
                else:
                    s3_client.download_file(
                        BUCKET,
                        shard_key,
                        output_file
                    )
                
                dl_duration = time.time() - dl_start
                total_bytes += file_size
                
                speed_mbps = (file_size / dl_duration) / (1024 * 1024)
                results.append(speed_mbps)
                
            except Exception as e:
                print(f"Worker {worker_id} (GPU {gpu_id}) download {i} failed: {e}", flush=True)
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        result = {
            'worker_id': worker_id,
            'gpu_id': gpu_id,
            'num_downloads': len(results),
            'total_bytes': total_bytes,
            'total_duration': total_duration,
            'avg_speed': statistics.mean(results) if results else 0,
            'speeds': results
        }
        
        result_queue.put(result)
        
    except Exception as e:
        print(f"Worker {worker_id} (GPU) process failed: {e}", flush=True)
        result_queue.put({'worker_id': worker_id, 'error': str(e)})


def download_on_cpu(worker_id, num_downloads, endpoint_url, multipart_config, result_queue):
    """Download shards with process pinned to specific CPU cores."""
    try:
        # Pin to CPU cores (no GPU required)
        # Each worker gets a range of CPU cores
        import os
        cpu_start = (worker_id * 8) % os.cpu_count()  # 8 cores per worker
        cpu_end = cpu_start + 8
        os.sched_setaffinity(0, range(cpu_start, min(cpu_end, os.cpu_count())))
        
        # Configure transfer based on multipart_config
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/customizations/s3.html#boto3.s3.transfer.TransferConfig
        # Flavors of multipart config :- [concurrency, threshold, chunksize]
        # max_concurrency: number of concurrent chunks
        # multipart_threshold: minimum size of a chunk
        # multipart_chunksize: size of a chunk
        # use_threads: use threads to download chunks
        if multipart_config == '250mb':
            transfer_config = TransferConfig(
                max_concurrency=4,
                multipart_threshold=128 * 1024 * 1024,  # 128 MB
                multipart_chunksize=250 * 1024 * 1024,  # 250 MB chunks
                use_threads=True
            )
        elif multipart_config == '256mb':
            transfer_config = TransferConfig(
                max_concurrency=4,
                multipart_threshold=128 * 1024 * 1024,  # 128 MB
                multipart_chunksize=256 * 1024 * 1024,  # 256 MB chunks
                use_threads=True
            )
        elif multipart_config == '512mb':
            transfer_config = TransferConfig(
                max_concurrency=4,
                multipart_threshold=256 * 1024 * 1024,  # 256 MB
                multipart_chunksize=512 * 1024 * 1024,  # 512 MB chunks
                use_threads=True
            )
        elif multipart_config == '1024mb':
            transfer_config = TransferConfig(
                max_concurrency=4,
                multipart_threshold=512 * 1024 * 1024,  # 512 MB
                multipart_chunksize=1024 * 1024 * 1024,  # 1024 MB chunks
                use_threads=True
            )
        elif multipart_config == '2048mb':
            transfer_config = TransferConfig(
                max_concurrency=4,
                multipart_threshold=1024 * 1024 * 1024,  # 1024 MB
                multipart_chunksize=2048 * 1024 * 1024,  # 2048 MB chunks
                use_threads=True
            )
        else:
            transfer_config = None
        
        # Create S3 client
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )
        
        results = []
        total_bytes = 0
        
        start_time = time.time()
        
        for i in range(num_downloads):
            shard_idx = (worker_id * num_downloads + i) % NUM_SHARDS
            shard_key = f"{PATH_PREFIX}shard_{shard_idx:06d}.dummy"
            output_file = OUTPUT_FILE
            
            try:
                # Get file size from S3 metadata
                head_response = s3_client.head_object(Bucket=BUCKET, Key=shard_key)
                file_size = head_response['ContentLength']
                
                dl_start = time.time()
                
                if transfer_config:
                    s3_client.download_file(
                        BUCKET,
                        shard_key,
                        output_file,
                        Config=transfer_config
                    )
                else:
                    s3_client.download_file(
                        BUCKET,
                        shard_key,
                        output_file
                    )
                
                dl_duration = time.time() - dl_start
                total_bytes += file_size
                
                speed_mbps = (file_size / dl_duration) / (1024 * 1024)
                results.append(speed_mbps)
                
            except Exception as e:
                print(f"Worker {worker_id} download {i} failed: {e}", flush=True)
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        result = {
            'worker_id': worker_id,
            'num_downloads': len(results),
            'total_bytes': total_bytes,
            'total_duration': total_duration,
            'avg_speed': statistics.mean(results) if results else 0,
            'speeds': results
        }
        
        result_queue.put(result)
        
    except Exception as e:
        print(f"Worker {worker_id} process failed: {e}", flush=True)
        result_queue.put({'worker_id': worker_id, 'error': str(e)})


def run_gpu_pinned_test(num_workers, downloads_per_worker, endpoint_url, endpoint_name, multipart_config=None):
    """Run concurrent downloads across multiple GPU-pinned workers."""
    num_gpus = torch.cuda.device_count()
    print(f"\n{'='*80}", flush=True)
    print(f"TEST: {endpoint_name} - {num_workers} workers x {downloads_per_worker} downloads (GPU-PINNED)", flush=True)
    print(f"Endpoint: {endpoint_url}", flush=True)
    print(f"GPUs available: {num_gpus}", flush=True)
    print(f"Workers per GPU: {num_workers // num_gpus if num_gpus > 0 else 0}", flush=True)
    if multipart_config:
        chunk_size = multipart_config.upper()
        print(f"Multipart: Yes (4 streams x {chunk_size} chunks)", flush=True)
    else:
        print(f"Multipart: No (single-threaded)", flush=True)
    print(f"{'='*80}", flush=True)
    
    result_queue = Queue()
    processes = []
    
    overall_start = time.time()
    
    # Spawn process for each worker (GPU-pinned)
    for worker_id in range(num_workers):
        p = Process(
            target=download_on_gpu,
            args=(worker_id, downloads_per_worker, endpoint_url, multipart_config, result_queue)
        )
        p.start()
        processes.append(p)
    
    # Wait for all processes
    for p in processes:
        p.join()
    
    overall_end = time.time()
    overall_duration = overall_end - overall_start
    
    # Collect results
    results = []
    while not result_queue.empty():
        results.append(result_queue.get())
    
    # Analyze
    successful = [r for r in results if 'error' not in r]
    
    if not successful:
        print(f"Error downloading shards", flush=True)
        return None
    
    total_bytes = sum(r['total_bytes'] for r in successful)
    total_data_gb = total_bytes / (1024 ** 3)
    
    aggregate_throughput_mbps = (total_bytes / overall_duration) / (1024 ** 2)
    aggregate_throughput_gbps = aggregate_throughput_mbps / 1024
    
    avg_per_worker = statistics.mean([r['avg_speed'] for r in successful])
    
    print(f"\nSUCCESSFULLY DOWNLOADED SHARDS", flush=True)
    print(f"   Workers: {len(successful)}/{num_workers}", flush=True)
    print(f"   Total data: {total_data_gb:.2f} GB", flush=True)
    print(f"   Duration: {overall_duration:.2f}s", flush=True)
    print(f"   Avg per worker: {avg_per_worker:.2f} MB/s", flush=True)
    print(f"   AGGREGATE: {aggregate_throughput_mbps:.2f} MB/s ({aggregate_throughput_gbps:.2f} GB/s)", flush=True)
    
    # Per-GPU breakdown
    if num_gpus > 0:
        print(f"\n   Per-GPU breakdown:", flush=True)
        for gpu_id in range(num_gpus):
            gpu_results = [r for r in successful if r.get('gpu_id') == gpu_id]
            if gpu_results:
                gpu_avg = statistics.mean([r['avg_speed'] for r in gpu_results])
                print(f"     GPU {gpu_id}: {len(gpu_results)} workers, {gpu_avg:.2f} MB/s avg", flush=True)
    
    # Per-worker breakdown (first 10 and last 10)
    print(f"\n   Per-worker breakdown (first 10 and last 10):", flush=True)
    sorted_results = sorted(successful, key=lambda x: x['worker_id'])
    for r in sorted_results[:10]:
        gpu_info = f" (GPU {r.get('gpu_id', '?')})" if 'gpu_id' in r else ""
        print(f"     Worker {r['worker_id']}{gpu_info}: {r['avg_speed']:.2f} MB/s ({r['num_downloads']} downloads)", flush=True)
    if len(sorted_results) > 20:
        print(f"     ... ({len(sorted_results) - 20} workers omitted) ...", flush=True)
    for r in sorted_results[-10:]:
        gpu_info = f" (GPU {r.get('gpu_id', '?')})" if 'gpu_id' in r else ""
        print(f"     Worker {r['worker_id']}{gpu_info}: {r['avg_speed']:.2f} MB/s ({r['num_downloads']} downloads)", flush=True)
    
    return {
        'endpoint_name': endpoint_name + " (GPU-pinned)",
        'num_workers': num_workers,
        'downloads_per_worker': downloads_per_worker,
        'successful_workers': len(successful),
        'total_data_gb': total_data_gb,
        'aggregate_throughput_gbps': aggregate_throughput_gbps,
        'avg_per_worker_mbps': avg_per_worker,
        'multipart_config': multipart_config,
        'pinning': 'GPU'
    }


def run_cpu_pinned_test(num_workers, downloads_per_worker, endpoint_url, endpoint_name, multipart_config=None):
    """Run concurrent downloads across multiple CPU-pinned workers."""
    print(f"\n{'='*80}", flush=True)
    print(f"TEST: {endpoint_name} - {num_workers} workers × {downloads_per_worker} downloads (CPU-PINNED)", flush=True)
    print(f"Endpoint: {endpoint_url}", flush=True)
    if multipart_config:
        chunk_size = multipart_config.upper()
        print(f"Multipart: Yes (4 streams × {chunk_size} chunks)", flush=True)
    else:
        print(f"Multipart: No (single-threaded)", flush=True)
    print(f"{'='*80}", flush=True)
    
    result_queue = Queue()
    processes = []
    
    overall_start = time.time()
    
    # Spawn process for each worker (CPU-pinned)
    for worker_id in range(num_workers):
        p = Process(
            target=download_on_cpu,
            args=(worker_id, downloads_per_worker, endpoint_url, multipart_config, result_queue)
        )
        p.start()
        processes.append(p)
    
    # Wait for all processes
    for p in processes:
        p.join()
    
    overall_end = time.time()
    overall_duration = overall_end - overall_start
    
    # Collect results
    results = []
    while not result_queue.empty():
        results.append(result_queue.get())
    
    # Analyze
    successful = [r for r in results if 'error' not in r]
    
    if not successful:
        print(f"Error downloading shards", flush=True)
        return None
    
    total_bytes = sum(r['total_bytes'] for r in successful)
    total_data_gb = total_bytes / (1024 ** 3)
    
    aggregate_throughput_mbps = (total_bytes / overall_duration) / (1024 ** 2)
    aggregate_throughput_gbps = aggregate_throughput_mbps / 1024
    
    avg_per_worker = statistics.mean([r['avg_speed'] for r in successful])
    
    print(f"\nSUCCESSFULLY DOWNLOADED SHARDS", flush=True)
    print(f"   Workers: {len(successful)}/{num_workers}", flush=True)
    print(f"   Total data: {total_data_gb:.2f} GB", flush=True)
    print(f"   Duration: {overall_duration:.2f}s", flush=True)
    print(f"   Avg per worker: {avg_per_worker:.2f} MB/s", flush=True)
    print(f"   AGGREGATE: {aggregate_throughput_mbps:.2f} MB/s ({aggregate_throughput_gbps:.2f} GB/s)", flush=True)
    
    # Per-worker breakdown
    print(f"\n   Per-worker breakdown:", flush=True)
    for r in sorted(successful, key=lambda x: x['worker_id']):
        print(f"     Worker {r['worker_id']}: {r['avg_speed']:.2f} MB/s ({r['num_downloads']} downloads)", flush=True)
    
    return {
        'endpoint_name': endpoint_name + " (CPU-pinned)",
        'num_workers': num_workers,
        'downloads_per_worker': downloads_per_worker,
        'successful_workers': len(successful),
        'total_data_gb': total_data_gb,
        'aggregate_throughput_gbps': aggregate_throughput_gbps,
        'avg_per_worker_mbps': avg_per_worker,
        'multipart_config': multipart_config,
        'pinning': 'CPU'
    }

def main():
    import os
    import sys
    
    # Check if GPU or CPU mode
    use_gpu_pinning = '--gpu' in sys.argv
    
    print("\n" + "="*80, flush=True)
    if use_gpu_pinning:
        print("GPU-PINNED BANDWIDTH TEST", flush=True)
        print("="*80, flush=True)
        print(f"GPUs available: {torch.cuda.device_count()}", flush=True)
        num_workers = torch.cuda.device_count() * 8  # 8 workers per GPU
    else:
        print("CPU-PINNED BANDWIDTH TEST", flush=True)
        print("="*80, flush=True)
        print(f"CPU cores available: {os.cpu_count()}", flush=True)
        num_workers = 128  # Test with high worker count to max out bandwidth
    
    downloads_per_worker = 8
    total_downloads = num_workers * downloads_per_worker
    
    print(f"Workers: {num_workers}", flush=True)
    print(f"Downloads per worker: {downloads_per_worker}", flush=True)
    print(f"Total concurrent downloads: {total_downloads}", flush=True)
    print(f"Bucket: {BUCKET}", flush=True)
    print(f"Shards: {NUM_SHARDS}", flush=True)
    print(f"Pinning mode: {'GPU' if use_gpu_pinning else 'CPU'}", flush=True)
    print(flush=True)
    
    results = []
    
    # Choose which test function to use
    test_func = run_gpu_pinned_test if use_gpu_pinning else run_cpu_pinned_test
    
    
    # Test 1: LOTA, single-threaded
    result = test_func(
        num_workers=num_workers,
        downloads_per_worker=downloads_per_worker,
        endpoint_url=LOTA_ENDPOINT,
        endpoint_name="LOTA (single-threaded)",
        multipart_config=None
    )
    if result:
        results.append(result)
    
    time.sleep(5)
    
    # Test 2: LOTA, 512MB chunks
    result = test_func(
        num_workers=num_workers,
        downloads_per_worker=downloads_per_worker,
        endpoint_url=LOTA_ENDPOINT,
        endpoint_name="LOTA (512MB chunks)",
        multipart_config='512mb'
    )
    if result:
        results.append(result)
    
    time.sleep(5)
    
    # Test 3: CAIOS, single-threaded
    result = test_func(
        num_workers=num_workers,
        downloads_per_worker=downloads_per_worker,
        endpoint_url=S3_ENDPOINT,
        endpoint_name="CAIOS (single-threaded)",
        multipart_config=None
    )
    if result:
        results.append(result)
    
    time.sleep(5)
    
    # Test 4: CAIOS, 512MB chunks
    result = test_func(
        num_workers=num_workers,
        downloads_per_worker=downloads_per_worker,
        endpoint_url=S3_ENDPOINT,
        endpoint_name="CAIOS (512MB chunks)",
        multipart_config='512mb'
    )
    if result:
        results.append(result)
    
    # Test 5: LOTA, 1024MB chunks
    result = test_func(
        num_workers=num_workers,
        downloads_per_worker=downloads_per_worker,
        endpoint_url=LOTA_ENDPOINT,
        endpoint_name="LOTA (1024MB chunks)",
        multipart_config='1024mb'
    )
    if result:
        results.append(result)

    time.sleep(5)
    
    # Test 6: LOTA, 2048MB chunks
    result = test_func(
        num_workers=num_workers,
        downloads_per_worker=downloads_per_worker,
        endpoint_url=LOTA_ENDPOINT,
        endpoint_name="LOTA (2048MB chunks)",
        multipart_config='2048mb'
    )
    if result:
        results.append(result)

    time.sleep(5)

    # Summary
    print("\n" + "="*80, flush=True)
    print(f"SUMMARY - {'GPU' if use_gpu_pinning else 'CPU'} Pinned Workers", flush=True)
    print("="*80, flush=True)
    print(f"{'Configuration':<45} {'Workers':<10} {'Aggregate':<20}", flush=True)
    print(f"{'-'*45} {'-'*10} {'-'*20}", flush=True)
    
    for r in results:
        name = r['endpoint_name']
        workers = r['successful_workers']
        agg = r['aggregate_throughput_gbps']
        print(f"{name:<45} {workers:<10} {agg:>10.2f} GB/s", flush=True)
    
    if results:
        best = max(results, key=lambda x: x['aggregate_throughput_gbps'])
        print(f"\nBest: {best['endpoint_name']} → {best['aggregate_throughput_gbps']:.2f} GB/s", flush=True)
    
    print("\n" + "="*80, flush=True)
    print("TEST COMPLETE", flush=True)
    print("="*80, flush=True)

if __name__ == "__main__":
    main()
