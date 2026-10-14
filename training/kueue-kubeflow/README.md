# Two-node PyTorch training with Kueue and Kubeflow Trainer

This example runs a 16-rank PyTorch all-reduce across two eight-GPU H100 nodes in one CKS cluster. Kueue queues the `TrainJob` until its full resource request can be admitted, and Kubeflow Trainer creates the distributed Pods. This is a single-cluster example and does not use MultiKueue.

## Prerequisites

- `kubectl` and Helm configured for a CKS cluster with two schedulable, InfiniBand-connected eight-GPU H100 nodes. Each node must expose at least 16 CPU, 128 GiB memory, eight `nvidia.com/gpu` devices, and one `rdma/ib` device. Keep the controller Pods schedulable on the cluster.
- Cluster permissions to install Helm charts, CRDs, and the queue resources below.
- Access from the training Pods to `nvcr.io/nvidia/pytorch:25.08-py3`.

The sample `ResourceFlavor` has no node selector, so use it as written only when the available GPU nodes are H100s. For a mixed GPU cluster, set `spec.nodeLabels` on the flavor to match the H100 NodePool before applying it. Size the queue quotas to your actual allocatable capacity.

## Install the controllers

Run these commands from this directory. The Trainer chart installs its JobSet dependency automatically and creates the `torch-distributed` runtime when enabled here. Install Trainer first so its CRDs exist when Kueue starts watching `TrainJob` resources.

```sh
helm install kubeflow-trainer oci://ghcr.io/kubeflow/charts/kubeflow-trainer \
  --version 2.2.1 --namespace kubeflow-system --create-namespace \
  --set runtimes.torchDistributed.enabled=true

helm repo add coreweave https://charts.core-services.ingress.coreweave.com
helm repo update coreweave
helm install kueue coreweave/cks-kueue \
  --version 2.0.0 --namespace kueue-system --create-namespace

kubectl -n kubeflow-system get deployments
kubectl -n kueue-system get deployments
kubectl get clustertrainingruntime torch-distributed
```

If either chart is already installed, keep the existing installation and confirm that Trainer v2, the `torch-distributed` runtime, and Kueue's `trainer.kubeflow.org/trainjob` integration are enabled. Use the [CoreWeave Kueue guide](https://docs.coreweave.com/products/cks/clusters/coreweave-charts/kueue) and [Kubeflow Trainer installation guide](https://trainer.kubeflow.org/en/latest/operator-guides/installation.html) for chart configuration.

## Create the queue and run the job

The example queue admits one two-node job at a time. Its quota covers 32 CPU, 256 GiB memory, 16 GPUs, and two RDMA allocations.

```sh
kubectl apply -f queue.yaml
kubectl get clusterqueue training
kubectl -n training get localqueue training

kubectl apply --dry-run=server -f trainjob.yaml
kubectl apply -f trainjob.yaml
kubectl -n training get trainjob,workloads.kueue.x-k8s.io,pods -w
```

The job writes a tiny all-reduce program into each Pod and runs eight ranks per node. It completes when every rank reports `sum=16`. To inspect the output and final state:

```sh
kubectl -n training logs -l jobset.sigs.k8s.io/jobset-name=two-node-h100-allreduce \
  --all-containers=true --prefix=true --tail=-1
kubectl -n training get trainjob two-node-h100-allreduce -o yaml
```

If the job stays queued, inspect `kubectl -n training describe workloads.kueue.x-k8s.io` and `kubectl describe clusterqueue training`. If Pods remain Pending, inspect their events and the nodes' GPU and RDMA allocatable resources. For a real training run, replace the inline program with a digest-pinned image containing your code and dependencies, and write checkpoints to durable storage.

References: [Kueue on CKS](https://docs.coreweave.com/products/cks/clusters/coreweave-charts/kueue), [Kueue TrainJob integration](https://kueue.sigs.k8s.io/docs/tasks/run/trainjobs/), [Kubeflow Trainer installation](https://trainer.kubeflow.org/en/latest/operator-guides/installation.html).
