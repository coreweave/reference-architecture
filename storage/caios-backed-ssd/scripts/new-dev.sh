#!/usr/bin/env bash
# Usage: USERNAME=jane ./scripts/new-dev.sh | kubectl apply -f -
# Add more env‑subst variables (bucket, region, etc.) as you like.
set -eu
source .env
DEV_USERNAME=${DEV_USERNAME:?Specify DEV_USERNAME env var}
envsubst < manifests/dev-env.yaml.template
