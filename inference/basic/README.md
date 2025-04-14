# Basic Inference Reference Architecture

This repository provides a Helm chart to deploy a basic inference setup on CoreWeave's infrastructure. Follow the steps below to set up the required dependencies in your cluster and install this chart.

## Prerequisites

Before installing this chart, ensure you have the following:
- A Kubernetes cluster on CoreWeave.
- `kubectl` and `helm` installed and configured to interact with your cluster.

## Setup

### 0. Add CoreWeave's Helm Repository
Add CoreWeave's Helm repository to your local Helm client:

```bash
helm repo add coreweave https://charts.core-services.ingress.coreweave.com
helm repo update
```

### 1. Install CoreWeave's Traefik Chart

CoreWeave's Traefik chart is required for ingress management. Install it using the following commands:

```bash
helm install traefik coreweave/traefik --namespace traefik --create-namespace
```

### 2. Install Cert-Manager and Configure Let's Encrypt ClusterIssuer

Cert-Manager is required to manage TLS certificates. Install it and configure the `letsencrypt-prod` ClusterIssuer:

#### Install Cert-Manager:

```bash
helm install cert-manager jetstack/cert-manager --namespace cert-manager --create-namespace
```

### 3. Verify Dependencies

Ensure that both Traefik and Cert-Manager are running correctly:

```bash
kubectl get pods -n traefik
kubectl get pods -n cert-manager
```

## Installing the Basic Inference Chart

Once the prerequisites are set up, you can install this chart:

```bash
helm install basic-inference ./ --namespace inference --create-namespace
```

## Cleanup

To uninstall the chart and its dependencies, run:

```bash
helm uninstall basic-inference --namespace inference
helm uninstall cert-manager --namespace cert-manager
helm uninstall traefik --namespace traefik
```
