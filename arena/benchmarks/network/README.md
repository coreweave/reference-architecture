# Network Benchmarks

Frontend network performance testing using iperf3.

## Enable iperf Deployment

The iperf server is deployed by the Helm chart when enabled:

```yaml
# values.yaml or --set flag
benchmarks:
  network:
    enabled: true
```

Or via helm install/upgrade:

```bash
helm upgrade --install ailabs ./charts/ailabs --set benchmarks.network.enabled=true
```

The chart creates:
- Namespace: `ailabs-benchmark-network`
- Deployment: `ailabs-iperf-server`
- Service: `ailabs-iperf-server` (ClusterIP, port 5201)
- IngressRouteTCP: `iperf.<clusterDomain>` via Traefik

Verify the deployment:

```bash
kubectl get pods -n ailabs-benchmark-network
kubectl get svc -n ailabs-benchmark-network
kubectl get ingressroutetcp -n ailabs-benchmark-network
```

## Running Tests

### From within the cluster (another pod)

```bash
# Get the service IP
IPERF_IP=$(kubectl get svc ailabs-iperf-server -n ailabs-benchmark-network -o jsonpath='{.spec.clusterIP}')

# Run a test pod
kubectl run iperf-client --rm -it --image=networkstatic/iperf3:latest -- -c $IPERF_IP
```

### From the login node (cluster network accessible)

```bash
# Get the service IP
IPERF_IP=$(kubectl get svc ailabs-iperf-server -n ailabs-benchmark-network -o jsonpath='{.spec.clusterIP}')

# TCP bandwidth test (default)
iperf3 -c $IPERF_IP

# TCP with parallel streams
iperf3 -c $IPERF_IP -P 4

# UDP bandwidth test
iperf3 -c $IPERF_IP -u -b 10G

# Extended duration test (60 seconds)
iperf3 -c $IPERF_IP -t 60

# Reverse mode (server sends to client)
iperf3 -c $IPERF_IP -R
```

### From external network (via Traefik Ingress)

The deployment includes a Traefik IngressRouteTCP for external access:

```bash
# Connect via the ingress hostname
iperf3 -c iperf.your-cluster.coreweave.app -p 443
```

Note: External iperf testing via ingress may have overhead. For accurate network benchmarks, test from within the cluster.

### Common iperf3 Options

| Option | Description |
|--------|-------------|
| `-c <host>` | Connect to server |
| `-P <n>` | Number of parallel streams |
| `-t <sec>` | Duration in seconds (default 10) |
| `-u` | UDP mode |
| `-b <rate>` | Target bandwidth (e.g., 10G, 1M) |
| `-R` | Reverse mode (server sends) |
| `-J` | JSON output |

## Cleanup

Disable via Helm:

```bash
helm upgrade ailabs ./charts/ailabs --set benchmarks.network.enabled=false
```

Or delete the namespace directly:

```bash
kubectl delete namespace ailabs-benchmark-network
```

## Expected Results

The iperf test measures TCP/UDP throughput between the client and server pod, representing frontend network capacity.
