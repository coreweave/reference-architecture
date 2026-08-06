# Kafka on CoreWeave local NVMe

<!-- customer-reference: entry-point -->
[Customer reference architecture](docs/customer-reference-architecture.md)

This non-production reference deploys Strimzi Kafka with dynamically provisioned, node-local storage below `/mnt/local/kafka`. It is a deployment starting point, not a production architecture, recovery procedure, or validation of CoreWeave availability, performance, or security.

## Important storage limits

`/mnt/local` is node-local storage. Treat its contents as lost when a node is lost or rebooted; Kubernetes PV/PVC identity does not make the underlying bytes durable. These manifests include no custom repair or cleanup automation.

The `kafka-local` StorageClass uses `Retain` and the node pools use `deleteClaim: false`. Removing Kafka can therefore leave PVs, PVCs, and local data behind. Reusing the same namespace and Kafka resource names can reuse the same PVC-named directories; plan cleanup and identity changes deliberately.

The provisioner creates directories and local PVs by running a Kubernetes helper Pod on the scheduled node. `WaitForFirstConsumer` ensures that node is selected first. The capacity check is read-only preflight guidance, not a quota: directory-backed local-path volumes can exceed their PVC request.

## Profiles

| Profile | Brokers | Controllers | Broker storage | Topic RF / min ISR |
|---|---:|---:|---:|---:|
| `two-node` | 2 | 3 | 400Gi each | 2 / 1 |
| `five-node` | 5 | 3 | 400Gi each | 5 / 3 |

Profiles are mutually exclusive and use the same resource names. The three controllers each request 20Gi.
The five-node profile also enables Cruise Control and uses larger CPU and memory requests than the two-node profile.

## Prerequisites

- A Kubernetes cluster on CoreWeave, with `/mnt/local` available on every selected node.
- `kubectl`, cluster-admin access for the local-path provisioner, and a Strimzi Cluster Operator configured to watch and reconcile the `kafka` namespace.
- At least two or five nodes, respectively, labelled `kafka.local/kafka-local=true`.
- Enough free node-local capacity for the requested claims and Kafka operational headroom.

Install the Strimzi operator using its [official installation instructions](https://strimzi.io/docs/operators/latest/deploying.html) before applying a profile.

## Deploy

From this directory:

```bash
kubectl apply -k provisioner/local-path
kubectl create namespace kafka --dry-run=client -o yaml | kubectl apply -f -
kubectl label node NODE_NAME kafka.local/kafka-local=true
./scripts/check-node-capacity.sh two-node
kubectl apply -k profiles/two-node
```

Use `five-node` in the last two commands for the five-broker profile. The capacity check reads selected nodes and mounts `/mnt/local` read-only; pass a profile name as shown and run it only once at a time.

Wait for the operator and Kafka resources to reconcile:

```bash
kubectl wait -n kafka --for=condition=Ready kafka/kafka-local --timeout=10m
kubectl wait -n kafka --for=condition=Ready kafkatopic/kafka-local-topic --timeout=10m
kubectl get kafka,kafkanodepool,kafkatopic,pvc -n kafka
kubectl get pods -n kafka -o wide
```

Confirm that each PV is local and bound to the node chosen for its consuming Kafka Pod:

```bash
kubectl get pv -o custom-columns=NAME:.metadata.name,PATH:.spec.local.path,NODE:.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0].values[0],CLAIM_NAMESPACE:.spec.claimRef.namespace,CLAIM_NAME:.spec.claimRef.name
```

After Kafka and `kafka-local-topic` are Ready, run the basic producer/readback check:

```bash
./scripts/smoke-test.sh
```

It verifies exact readback of a small uniquely tagged message set produced with `acks=all`; it does not test node loss, reboot recovery, HA, performance, or security.

## Validate manifests

```bash
./scripts/validate.sh
kubectl apply --dry-run=server -k provisioner/local-path
kubectl apply --dry-run=server -k profiles/two-node
```

The server dry run is optional and requires a cluster with the Strimzi CRDs installed. Run it again with `profiles/five-node` when using that profile.

## Package license

This package is governed by [LICENSE](LICENSE) (Apache-2.0) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
