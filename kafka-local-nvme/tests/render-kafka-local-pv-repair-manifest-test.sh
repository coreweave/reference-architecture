#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
r="$root/scripts/render-kafka-local-pv-repair-manifest.sh"
t="$(mktemp -d)";trap 'rm -rf "$t"' EXIT
printf 'node-a\thost-a\t12345678-abcd\tcloud://node-a\n' > "$t/nodes"
a=(--image registry.example/repair@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa --mount-fs ext4 --mount-source /dev/nvme0n1 --mount-options nodev,nosuid --nodes "$t/nodes")
"$r" "${a[@]}" > "$t/out"
for kind in ServiceAccount Role RoleBinding ConfigMap ClusterRole ClusterRoleBinding DaemonSet; do grep -q "kind: $kind" "$t/out"; done
awk '/^kind: ClusterRoleBinding$/{in_binding=1} in_binding && /^roleRef:/{in_role_ref=1} in_role_ref && /^  name: kafka-local-pv-repair-reader$/{found=1} END{exit(found ? 0 : 1)}' "$t/out"
grep -q 'immutable: true' "$t/out";grep -q 'updateStrategy: {type: OnDelete}' "$t/out";grep -q 'hostPID: true' "$t/out";grep -q 'readOnlyRootFilesystem: true' "$t/out";grep -q 'type: RuntimeDefault' "$t/out";grep -q 'resourceNames: \["node-a"\]' "$t/out";grep -q 'hostPath: {path: /mnt/local, type: Directory}' "$t/out";grep -q 'verbs: \["get", "list", "watch"\]' "$t/out";grep -q 'resources: \["persistentvolumeclaims"\]' "$root/provisioner/local-path/repair/rbac.yaml";! grep -Eq 'verbs:.*(create|update|patch|delete)' "$t/out"
! "$r" --image bad --mount-fs ext4 --mount-source /dev/x --mount-options nosuid --nodes "$t/nodes" >/dev/null 2>&1
! "$r" --image "${a[1]}" --mount-fs ext4 --mount-source /dev/x --mount-options nosuid,nosuid --nodes "$t/nodes" >/dev/null 2>&1
printf 'node-a\thost-b\t12345678-abcd\tcloud://node-b\n' >> "$t/nodes";! "$r" "${a[@]}" >/dev/null 2>&1
