# Kafka on CoreWeave local NVMe: customer reference

## Scope and status

<!-- customer-reference: status=non-production-reference -->

This is a non-production deployment reference for Strimzi Kafka using CoreWeave node-local storage. It supplies a local-path provisioner configuration and two mutually exclusive Kafka profiles. It does not claim recovery from node loss or reboot, CoreWeave validation, HA, performance, security, compliance, or production readiness.

## What it deploys

The local-path provisioner creates a helper Pod after scheduling selects a node. The helper writes a PVC-named directory under `/mnt/local/kafka`, and the provisioner creates a local PV with node affinity. `WaitForFirstConsumer` prevents provisioning before that node is selected.

| Profile | Brokers | Controllers | Topic RF / min ISR |
|---|---:|---:|---:|
| `two-node` | 2 | 3 | 2 / 1 |
| `five-node` | 5 | 3 | 5 / 3 |

Both profiles select nodes labelled `kafka.local/kafka-local=true`, use hostname placement, and create 400Gi broker claims plus 20Gi controller claims. They share names and cannot be installed together.
The five-node profile enables Cruise Control and uses larger CPU and memory requests than the two-node profile.

## Storage lifecycle

`/mnt/local` is node-local and volatile: loss or reboot of a node can make its data unavailable. A local PV and its PVC keep Kubernetes identity during ordinary Pod replacement on the same running node; they do not preserve data through node loss or reboot.

The StorageClass has `Retain`, and Strimzi node pools set `deleteClaim: false`. Deleting Kafka can leave PVs, PVCs, and local directories. A later deployment with the same namespace and PVC names may encounter or reuse those directories. Establish an operations and data-retention process before use.

PVC sizes are not hard limits for directory-backed local-path volumes: directory-backed local-path PVC requests neither reserve nor enforce `/mnt/local` capacity. Operators must independently verify available capacity and leave operational headroom on every selected node.

## Deployment and verification

Install Strimzi, apply `provisioner/local-path`, label the intended nodes, and apply one profile. See the [package README](../README.md) for commands.

Verify that PVCs bind, Kafka resources become Ready, and every PV reports a local path and node affinity consistent with its Kafka Pod. The included [smoke test](../scripts/smoke-test.sh) produces with `acks=all` and verifies exact readback of a uniquely tagged message set. It is a basic deployment check only.

## Optional repair boundary

The repository does not install the Repair DaemonSet through its normal Kustomizations. When explicitly rendered and applied, it is a privileged host-storage component: it uses `hostPID` to inspect `/proc/1/mountinfo` and a read-write hostPath for `/mnt/local`. Its trust boundary requires a Pod Security exception, deliberate operator ownership, and serialized maintenance.

The agent may recreate only missing components of the exact managed directory hierarchy for a Bound local PV with an authorized same Node identity and a verified host mount signature. It does not restore data, delete directories, or write Kubernetes PV/PVC objects. Newly created components are mode `0770` and assigned UID `1001`/GID `0`; existing components are left untouched. Kafka rebuilds only from healthy replicas; this is not a claim of automatic reboot or replacement recovery, cleanup, or provider validation. It runs as root solely to create those missing components, with only `CHOWN` and `DAC_OVERRIDE` added after dropping all capabilities.

Operators build and publish the image themselves, then render with its immutable digest. The Docker build runs Linux tests. Rendering requires Python 3, a captured exact Node name/hostname/UID/provider-ID allowlist, and independently verified mount filesystem, source, and canonical sorted options excluding `ro`/`rw`. Any identity mismatch requires reauthorization and a newly rendered ConfigMap; the changed Pod template rolls the DaemonSet automatically. Check rollout status and logs, and keep maintenance serialized. The two-node profile can lose controller quorum; simultaneous loss can be unrecoverable.

## Customer decisions before deployment

- Whether node-local loss is acceptable and what replication, backup, and recovery design is required.
- Node selection, capacity reservation, quotas, monitoring, and operational headroom.
- Secure listener exposure, network policy, authentication, authorization, encryption, observability, and lifecycle ownership.
- A controlled retained-storage and decommissioning process that avoids unintended same-name reuse.
