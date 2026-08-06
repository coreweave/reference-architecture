#!/usr/bin/env bash
set -euo pipefail

namespace="${NAMESPACE:-kafka}"
cluster="${KAFKA_CLUSTER:-kafka-local}"
topic="${KAFKA_TOPIC:-kafka-local-topic}"
message_count="${MESSAGE_COUNT:-10}"
kafka_image="${KAFKA_IMAGE:-quay.io/strimzi/kafka:1.1.0-kafka-4.3.0}"
bootstrap="${cluster}-kafka-bootstrap:9092"
run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
producer_pod="kafka-local-producer-$$"
consumer_pod="kafka-local-consumer-$$"
consumer_output="$(mktemp)"
expected_messages="$(mktemp)"
consumed_messages="$(mktemp)"

cleanup() {
  kubectl --namespace "$namespace" delete pod \
    "$producer_pod" "$consumer_pod" \
    --ignore-not-found \
    --wait=false >/dev/null 2>&1 || true
  rm -f "$consumer_output" "$expected_messages" "$consumed_messages"
}
trap cleanup EXIT

if [[ ! "$message_count" =~ ^[1-9][0-9]*$ ]]; then
  printf 'MESSAGE_COUNT must be a positive integer.\n' >&2
  exit 2
fi

kubectl --namespace "$namespace" wait \
  --for=condition=Ready \
  "kafkatopic/${topic}" \
  --timeout=300s

printf 'Producing %s messages with run ID %s\n' "$message_count" "$run_id"

for message_number in $(seq 1 "$message_count"); do
  printf '%s\n' \
    "${run_id}|message=${message_number}|timestamp=$(date -u +%FT%TZ)"
done > "$expected_messages"

kubectl run "$producer_pod" \
    --namespace "$namespace" \
    --image "$kafka_image" \
    --restart Never \
    --attach=true \
    --pod-running-timeout=5m \
    --overrides='{"spec":{"tolerations":[{"key":"dedicated","operator":"Equal","value":"kafka","effect":"NoSchedule"}]}}' \
    -i < "$expected_messages" \
    --command -- \
    bin/kafka-console-producer.sh \
      --bootstrap-server "$bootstrap" \
      --topic "$topic" \
      --command-property acks=all

kubectl --namespace "$namespace" wait \
  --for=jsonpath='{.status.phase}'=Succeeded \
  "pod/${producer_pod}" \
  --timeout=60s

printf 'Reading messages back from %s\n' "$topic"

kubectl run "$consumer_pod" \
  --namespace "$namespace" \
  --image "$kafka_image" \
  --restart Never \
  --attach=true \
  --pod-running-timeout=5m \
  --overrides='{"spec":{"tolerations":[{"key":"dedicated","operator":"Equal","value":"kafka","effect":"NoSchedule"}]}}' \
  -i \
  --command -- \
  bin/kafka-console-consumer.sh \
    --bootstrap-server "$bootstrap" \
    --topic "$topic" \
    --from-beginning \
    --timeout-ms 15000 \
  >"$consumer_output" 2>/dev/null || true

grep -F "$run_id" "$consumer_output" > "$consumed_messages" || true

if ! diff --brief \
  <(LC_ALL=C sort "$expected_messages") \
  <(LC_ALL=C sort "$consumed_messages") >/dev/null; then
  printf 'Exact readback failed for run ID %s.\n' "$run_id" >&2
  diff -u \
    <(LC_ALL=C sort "$expected_messages") \
    <(LC_ALL=C sort "$consumed_messages") >&2 || true
  exit 1
fi

printf 'Successfully produced and exactly read %s messages for %s\n' \
  "$message_count" "$run_id"
