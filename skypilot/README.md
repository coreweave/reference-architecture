# SkyPilot Configuration Examples

This directory contains example SkyPilot configuration files demonstrating different use cases for running workloads on CoreWeave infrastructure.

## Configuration Examples

### 1. mydevpod.yaml

A development environment configuration that sets up a containerized workspace for interactive development and testing.

**Use Case:** Interactive development, experimentation, and testing with GPU acceleration.

### 2. vllm.yaml

A production-ready configuration for deploying vLLM inference servers with OpenAI-compatible API endpoints.

**Use Case:** Production inference serving with OpenAI-compatible API for language models.

### 3. distributed_training.yaml

A multi-node distributed training configuration using PyTorch's Distributed Data Parallel (DDP) framework.

**Use Case:** Large-scale distributed training across multiple nodes for computationally intensive models.

### 4. my-caios-devpod.yaml

A development environment configuration demonstrating CoreWeave Object Storage (CAIOS) integration with boto3 for reading, writing, and listing objects. If you have not yet configured CAIOS credentials, please follow the guidance in [this section](https://github.com/coreweave/reference-architecture/tree/main/storage/caios-credentials) to automatically configure CAIOS credentials. 

**Use Case:** Testing and validating CAIOS bucket access with AWS-compatible tools in a GPU-accelerated development environment. 

## Getting Started

To use any of these configurations:

1. Ensure you have SkyPilot installed and configured for CoreWeave
2. Modify the configuration parameters as needed for your specific requirements
3. Launch the configuration using: `sky launch <config-file.yaml>`

For more information on SkyPilot and CoreWeave integration, refer to the main documentation.