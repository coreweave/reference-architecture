#!/usr/bin/env bash
# Validate the checked-in deployment manifests without a cluster.
set -euo pipefail

script_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root_directory="$(cd "$script_directory/.." && pwd)"
temporary_directory="$(mktemp -d)"
trap 'rm -rf "$temporary_directory"' EXIT

command -v kubectl >/dev/null 2>&1 || {
  printf 'kubectl is required for Kustomize rendering.\n' >&2
  exit 1
}

command -v python3 >/dev/null 2>&1 || {
  printf 'python3 is required for repair manifest rendering.\n' >&2
  exit 1
}

command -v go >/dev/null 2>&1 || {
  printf 'go is required for Go test and vet validation.\n' >&2
  exit 1
}

fail() {
  printf 'Validation error: %s\n' "$1" >&2
  exit 1
}

for script in "$script_directory"/*.sh; do
  bash -n "$script" || fail "invalid Bash syntax: ${script#$root_directory/}"
done
bash -n "$root_directory/tests/render-kafka-local-pv-repair-manifest-test.sh" || fail 'invalid renderer test syntax'
"$root_directory/tests/render-kafka-local-pv-repair-manifest-test.sh" || fail 'renderer test failed'

(
  cd "$root_directory"
  GOCACHE="$temporary_directory/go-build" go test ./... || exit 1
  GOCACHE="$temporary_directory/go-build" GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go test -c ./internal/repair -o "$temporary_directory/repair-linux.test" || exit 1
  GOCACHE="$temporary_directory/go-build" GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go vet ./internal/repair ./cmd/kafka-local-pv-repair || exit 1
) || fail 'Go validation failed'

provisioner="$temporary_directory/provisioner.yaml"
two_node="$temporary_directory/two-node.yaml"
five_node="$temporary_directory/five-node.yaml"
kubectl kustomize "$root_directory/provisioner/local-path" > "$provisioner"
kubectl kustomize "$root_directory/profiles/two-node" > "$two_node"
kubectl kustomize "$root_directory/profiles/five-node" > "$five_node"

require() {
  local file="$1" pattern="$2" description="$3"
  grep -Eq -- "$pattern" "$file" || fail "$description"
}

require_count() {
  local file="$1" pattern="$2" expected="$3" description="$4" actual
  actual="$(grep -Ec -- "$pattern" "$file" || true)"
  [[ "$actual" -eq "$expected" ]] || fail "$description (found $actual, expected $expected)."
}

require_resource() {
  local file="$1" kind="$2" pattern="$3" description="$4"
  awk -v kind="$kind" -v pattern="$pattern" '
    function check() {
      if (resource_kind == kind && resource ~ pattern) found = 1
    }
    /^---$/ { check(); resource_kind = ""; resource = ""; next }
    { resource = resource $0 "\n" }
    $0 == "kind: " kind { resource_kind = kind }
    END { check(); exit(found ? 0 : 1) }
  ' "$file" || fail "$description"
}

require_node_pool() {
  local file="$1" role="$2" replicas="$3" size="$4" description="$5"
  awk -v role="$role" -v replicas="$replicas" -v size="$size" '
    function check() {
      if (kind == "KafkaNodePool" && has_role && has_replicas && has_size && has_class && has_delete_claim) found = 1
    }
    /^---$/ { check(); kind = ""; has_role = has_replicas = has_size = has_class = has_delete_claim = 0; next }
    $0 == "kind: KafkaNodePool" { kind = "KafkaNodePool" }
    kind == "KafkaNodePool" && $0 == "  - " role { has_role = 1 }
    kind == "KafkaNodePool" && $0 == "  replicas: " replicas { has_replicas = 1 }
    kind == "KafkaNodePool" && $0 == "    size: " size { has_size = 1 }
    kind == "KafkaNodePool" && $0 == "    class: kafka-local" { has_class = 1 }
    kind == "KafkaNodePool" && $0 == "    deleteClaim: false" { has_delete_claim = 1 }
    END { check(); exit(found ? 0 : 1) }
  ' "$file" || fail "$description"
}

require "$provisioner" 'nodePath: /mnt/local/kafka' 'StorageClass must use /mnt/local/kafka.'
require "$provisioner" 'reclaimPolicy: Retain' 'StorageClass must retain PVs.'
require "$provisioner" 'volumeBindingMode: WaitForFirstConsumer' 'StorageClass must wait for a consumer.'
require "$provisioner" 'defaultVolumeType: local' 'StorageClass must create local PVs.'
require "$provisioner" '"/mnt/local/kafka"' 'Provisioner ConfigMap must restrict helper Pods to /mnt/local/kafka.'

validate_profile() {
  local file="$1" brokers="$2" topic_replicas="$3" min_isr="$4" profile="$5"
  require_count "$file" '^kind: KafkaNodePool$' 2 "$profile must define broker and controller pools"
  require_count "$file" '^kind: KafkaTopic$' 1 "$profile must define one topic"
  require_node_pool "$file" broker "$brokers" 400Gi "$profile broker pool is incorrect."
  require_node_pool "$file" controller 3 20Gi "$profile controller pool is incorrect."
  require_resource "$file" KafkaTopic "replicas: ${topic_replicas}" "$profile topic replication factor is incorrect."
  require_resource "$file" KafkaTopic "min.insync.replicas: ${min_isr}" "$profile topic min ISR is incorrect."
  require "$file" 'key: kafka.local/kafka-local' "$profile must select labelled Kafka nodes."
  require "$file" 'topologyKey: kubernetes.io/hostname' "$profile must use hostname placement."
}

validate_profile "$two_node" 2 2 1 two-node
validate_profile "$five_node" 5 5 3 five-node
printf 'Manifest validation passed.\n'
