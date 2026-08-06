#!/usr/bin/env bash
set -euo pipefail

# Checks both the profile's conservative maximum requested storage per node
# and the current bytes beneath /mnt/local/kafka against a 50% ceiling.
#
# This is a deployment and monitoring guard. Rancher Local Path Provisioner
# does not enforce the size of a directory-backed PVC, so this script is not a
# hard quota and cannot prevent growth between checks.

script_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root_directory="$(cd "$script_directory/.." && pwd)"

profile="${1:-}"
namespace="${NAMESPACE:-kafka}"
ceiling_percent=50
capacity_manifest="$root_directory/checks/node-local-capacity.yaml"
daemonset_name="kafka-local-capacity-check"
daemonset_applied=false

remove_capacity_daemonset() {
  if [[ "$daemonset_applied" == true ]]; then
    kubectl --namespace "$namespace" delete daemonset "$daemonset_name" \
      --ignore-not-found \
      --wait=true \
      --timeout=2m >/dev/null 2>&1 || true
  fi
}
trap remove_capacity_daemonset EXIT

usage() {
  printf 'Usage: %s two-node|five-node\n' "$(basename "$0")" >&2
}

case "$profile" in
  two-node)
    expected_node_count=2
    # Controller anti-affinity is preferred because three controllers must fit
    # on two nodes. Use all three controllers as the conservative upper bound.
    worst_case_controllers_per_node=3
    ;;
  five-node)
    expected_node_count=5
    # Required controller anti-affinity permits at most one per selected node.
    worst_case_controllers_per_node=1
    ;;
  *)
    usage
    exit 2
    ;;
esac

command -v kubectl >/dev/null 2>&1 || {
  printf 'kubectl is required.\n' >&2
  exit 1
}

if [[ ! -f "$capacity_manifest" ]]; then
  printf 'Capacity-check manifest not found: %s\n' "$capacity_manifest" >&2
  exit 1
fi

read_claim_size_gi() {
  local manifest="$1"
  local size

  size="$(
    awk '
      $1 == "size:" {
        value = $2
        sub(/Gi$/, "", value)
        print value
        exit
      }
    ' "$manifest"
  )"

  if [[ -z "$size" || "$size" == *[!0-9]* ]]; then
    printf 'Expected a whole-Gi storage size in %s.\n' "$manifest" >&2
    exit 1
  fi

  printf '%s\n' "$size"
}

broker_size_gi="$(
  read_claim_size_gi "$root_directory/profiles/$profile/brokers.yaml"
)"
controller_size_gi="$(
  read_claim_size_gi "$root_directory/profiles/$profile/controllers.yaml"
)"
planned_gi="$(
  printf '%s\n' \
    $((broker_size_gi + controller_size_gi * worst_case_controllers_per_node))
)"
planned_kib=$((planned_gi * 1024 * 1024))

selected_nodes=()
selected_node_count=0
while IFS= read -r node_resource; do
  if [[ -n "$node_resource" ]]; then
    selected_nodes+=("$node_resource")
    selected_node_count=$((selected_node_count + 1))
  fi
done < <(
  kubectl get nodes \
    --selector kafka.local/kafka-local=true \
    --output name
)

if [[ "$selected_node_count" -ne "$expected_node_count" ]]; then
  printf 'Capacity check requires exactly %s selected nodes for %s; found %s.\n' \
    "$expected_node_count" "$profile" "$selected_node_count" >&2
  if [[ "$selected_node_count" -gt 0 ]]; then
    printf 'Selected nodes:\n' >&2
    printf '  %s\n' "${selected_nodes[@]}" >&2
  fi
  exit 1
fi

printf '%s\n' \
  "Profile: ${profile}" \
  "Selected nodes: ${selected_node_count}" \
  "Broker request: ${broker_size_gi} GiB" \
  "Controller request: ${controller_size_gi} GiB" \
  "Conservative per-node request: ${planned_gi} GiB" \
  "Ceiling: ${ceiling_percent}% of each node's /mnt/local capacity"

kubectl --namespace "$namespace" apply --filename "$capacity_manifest"
daemonset_applied=true

capacity_pods=()
capacity_pod_count=0
pod_creation_deadline=$((SECONDS + 300))
while true; do
  capacity_pods=()
  capacity_pod_count=0
  while IFS= read -r pod_resource; do
    if [[ -n "$pod_resource" ]]; then
      capacity_pods+=("$pod_resource")
      capacity_pod_count=$((capacity_pod_count + 1))
    fi
  done < <(
    kubectl --namespace "$namespace" get pods \
      --selector app.kubernetes.io/name=kafka-local-capacity-check \
      --output name
  )

  if [[ "$capacity_pod_count" -eq "$selected_node_count" ]]; then
    break
  fi

  if [[ "$SECONDS" -ge "$pod_creation_deadline" ]]; then
    printf 'Timed out waiting for %s capacity-check Pods; found %s.\n' \
      "$selected_node_count" "$capacity_pod_count" >&2
    exit 1
  fi

  sleep 2
done

kubectl --namespace "$namespace" wait \
  --for=condition=Ready \
  "${capacity_pods[@]}" \
  --timeout=10m

printf '\n%-32s %10s %10s %10s %10s %10s\n' \
  NODE TOTAL_GiB USED_GiB FREE_GiB KAFKA_GiB PLAN_PCT

failure_count=0
result_count=0
while IFS=$'\t' read -r pod_name node_name; do
  [[ -n "$pod_name" ]] || continue
  result_count=$((result_count + 1))

  capacity_line="$(
    kubectl --namespace "$namespace" logs "$pod_name" \
      --container capacity-check |
      awk '/^KAFKA_LOCAL_CAPACITY / { print; exit }'
  )"

  total_kib=
  used_kib=
  available_kib=
  kafka_kib=
  for field in $capacity_line; do
    case "$field" in
      total_kib=*) total_kib="${field#total_kib=}" ;;
      used_kib=*) used_kib="${field#used_kib=}" ;;
      available_kib=*) available_kib="${field#available_kib=}" ;;
      kafka_kib=*) kafka_kib="${field#kafka_kib=}" ;;
    esac
  done

  if [[ -z "$total_kib" || -z "$used_kib" || \
        -z "$available_kib" || -z "$kafka_kib" ]]; then
    printf 'Invalid capacity result from %s on %s: %s\n' \
      "$pod_name" "$node_name" "$capacity_line" >&2
    failure_count=$((failure_count + 1))
    continue
  fi

  ceiling_kib=$((total_kib * ceiling_percent / 100))
  planned_tenths=$((planned_kib * 1000 / total_kib))

  printf '%-32s %10s %10s %10s %10s %9s.%s%%\n' \
    "$node_name" \
    "$((total_kib / 1024 / 1024))" \
    "$((used_kib / 1024 / 1024))" \
    "$((available_kib / 1024 / 1024))" \
    "$((kafka_kib / 1024 / 1024))" \
    "$((planned_tenths / 10))" \
    "$((planned_tenths % 10))"

  if [[ "$planned_kib" -gt "$ceiling_kib" ]]; then
    printf 'FAIL %s: planned %s GiB exceeds the %s%% ceiling.\n' \
      "$node_name" "$planned_gi" "$ceiling_percent" >&2
    failure_count=$((failure_count + 1))
  fi

  if [[ "$planned_kib" -gt "$available_kib" ]]; then
    printf 'FAIL %s: only %s GiB is currently available for a %s GiB plan.\n' \
      "$node_name" "$((available_kib / 1024 / 1024))" "$planned_gi" >&2
    failure_count=$((failure_count + 1))
  fi

  if [[ "$kafka_kib" -gt "$ceiling_kib" ]]; then
    printf 'FAIL %s: /mnt/local/kafka currently exceeds the %s%% ceiling.\n' \
      "$node_name" "$ceiling_percent" >&2
    failure_count=$((failure_count + 1))
  fi
done < <(
  kubectl --namespace "$namespace" get pods \
    --selector app.kubernetes.io/name=kafka-local-capacity-check \
    --output jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.nodeName}{"\n"}{end}'
)

if [[ "$result_count" -ne "$selected_node_count" ]]; then
  printf 'Expected %s node results, received %s.\n' \
    "$selected_node_count" "$result_count" >&2
  failure_count=$((failure_count + 1))
fi

if [[ "$failure_count" -ne 0 ]]; then
  printf 'Capacity check failed with %s violation(s).\n' \
    "$failure_count" >&2
  exit 1
fi

printf '%s\n' \
  'Capacity check passed on every selected node.' \
  'Reminder: this check detects violations but does not enforce a hard quota.'
