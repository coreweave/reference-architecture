# Warp Benchmark

This directory contains tools for running storage performance benchmarks using [MinIO Warp](https://github.com/minio/warp) against CoreWeave's AI Object Storage.

## Overview

The `warp-benchmark` shell script automates the setup and configuration of Warp benchmarks on CoreWeave Kubernetes clusters. It streamlines the process of testing object storage performance by automatically gathering cluster information, configuring credentials, and generating the necessary Helm chart values.

## Prerequisites

You must have a valid KUBECONFIG, and at least one bucket already set up with policies that allow you to read/write to it. This means that you must have created an organizational policy, and created a bucket. 

## Benchmarking

The `warp-benchmark` script collects information about your Kubernetes cluster for creating a warp configuration file. 
If environment variables (`ACCESS_KEY_ID` and `SECRET_KEY`) are set, it will use those variables for storage access. Alternatively, it can create a key to configure the benchmark. 

It will fetches and displays all available object storage buckets
and prompt the user to select a target bucket for benchmarking.

The default number of replicas is calculated based on GPU nodes (GPU nodes - 1). This can be overriden. Note that each replica should run as a pod on a different node, with one node reserved for the controller. 

A base warp configuration template (optimized for 2 GB200 nodes) is downloaded from the reference architecture repository and modified with:
  - Replica count
  - Cluster region
  - Target bucket name
  - Access credentials

This creates a `warp-config-generated.yaml` file and instructions for installing and running warp.

Other parameters that you may want to modify are benchmark (default is get, but you may choose put or mixed), concurrency (300 works well on a GB200) and object size (50MiB performs well). 

## Links

For issues or questions about CoreWeave Object Storage or the Warp benchmark tool, please refer to:
- [CoreWeave Documentation](https://docs.coreweave.com)
- [MinIO Warp GitHub Repository](https://github.com/minio/warp)
- [CAIOS Achieves 7 GB/s per GPU on NVIDIA Blackwell Ultra](https://www.coreweave.com/blog/caios-achieves-7-gb-s-per-gpu-on-nvidia-blackwell-ultra)
- [Benchmark Results: CoreWeave AI Object Storage Delivers 2 GB/s per GPU Throughput](https://www.coreweave.com/blog/benchmark-results-coreweave-ai-object-storage-delivers-2-gb-s-per-gpu-throughput-across-any-number-of-gpus)
