#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tag="${1:-kafka-local-pv-repair:dev}"
(cd "$root" && docker run --rm --mount type=bind,src="$root",dst=/src --workdir /src golang:1.24-alpine go test ./...)
(cd "$root" && docker build -t "$tag" .)
