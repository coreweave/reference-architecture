# Observability Setup

This sample installs **Prometheus** and **Grafana** for observability in your Kubernetes cluster. This folder contains a Helm chart that sets up these components with Traefik ingress and cert-manager as dependencies for ingress and TLS management.

## Prerequisites

- Kubernetes cluster
- [Helm](https://helm.sh/) installed
- Traefik ingress controller installed (From coreweave docs)
- Cert-manager installed (From coreweave docs)

## Components

- **Prometheus**: Collects and stores metrics from your cluster and workloads.
- **Grafana**: Visualizes metrics and dashboards.

## Installation

1. **Add Helm repositories** (if needed):

```sh
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
```

2. **Install the dependency charts**:
You need to install Traefik and cert-manager before installing this chart. If you haven't done so, follow the instructions in the CoreWeave documentation to install Traefik and cert-manager.

First install Traefik:
```sh
helm install traefik coreweave/traefik --namespace traefik --create-namespace
```

Then install cert-manager (this needs to happen in two steps):
```sh
helm install cert-manager coreweave/cert-manager --namespace cert-manager --create-namespace
helm upgrade cert-manager coreweave/cert-manager --namespace cert-manager --set cert-issuers.enabled=true 
```

3. **Install this chart**:
The default values won't work out of the box because you need to add CLUSTER_ORG and CLUSTER_NAME to the values.yaml file. You can do this by replacing the values.yaml file directly, or overriding them with another file or command line arguments.

**OPTIONAL**: If you want to enable external access to query metrics from a source outside your cluster (i.e., not the cluster Grafana), you'll need to set the `prometheus.externalAccess.enabled` value to true and update the credentials (unless you want to keep the default ones). The default values are username `admin` and password `cwadmin`. You can set it in the `values.yaml` file under `prometheus.externalAccess.credentials`; however, it needs to be hashed. To hash one yourself, you can run the following command in any machine (you can install `htpasswd` by intalling the `apache2-utils` package on Debian/Ubuntu or `httpd-tools` on CentOS/RHEL):

```sh
USERNAME=admin
PASSWORD=cwadmin
htpasswd -nb $USERNAME $PASSWORD
```

This will output a hashed password that you can use in the `values.yaml` file.

Note that you don't need to set the `prometheus.externalAccess.enabled` value if you only want to see metrics in the Grafana instance we will deploy with this sample.

If you haven't already, get the dependencies for this chart:

```sh
helm dependency build
```

Once your values are set, you can install the chart with:

```sh
helm install observability ./ --namespace monitoring --create-namespace 
```

> Replace `./` with the path to this chart if running from a different directory.

4. **Access Grafana**:

The chart creates an Ingress for Grafana using Traefik and TLS is managed by cert-manager.

To get the credentials to Grafana, you must run the following command:
```sh
kubectl get secret observability-grafana -n monitoring -o=jsonpath='{.data.admin-password}' | base64 --decode; echo
```

To get the endpoint

**NOTE**: This assumes you used the default namespace `monitoring` and default release name `observability`. If you used different values, update the commands.

## Configuration

You can customize values in `values.yaml` to suit your environment.

## Cleaning up

To remove the chart:
```sh
helm uninstall observability --namespace monitoring
```

To remove the monitoring namespace:
```sh
kubectl delete namespace monitoring
```

To remove Traefik and cert-manager, you can run:
```sh
helm uninstall traefik --namespace traefik
helm uninstall cert-manager --namespace cert-manager
kubectl delete namespace traefik
kubectl delete namespace cert-manager
```
