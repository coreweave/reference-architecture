#!/bin/bash
#
# Create the source and destination CAIOS buckets, each pinned to its own
# Availability Zone via LocationConstraint. Idempotent: a bucket that already
# exists and is owned by you is left untouched.
#
# Prerequisites:
#   - AWS CLI installed.
#   - CAIOS access key available, either exported in the environment
#     (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY) or in caios-keys.env, which
#     this script will source automatically.
#
# Required configuration (set via environment variables):
#   SRC_BUCKET   source bucket name        (globally unique)
#   SRC_AZ       source Availability Zone  (e.g. US-EAST-04A)
#   DST_BUCKET   destination bucket name   (globally unique)
#   DST_AZ       dest Availability Zone    (a different region's AZ)
#
# See the supported AZ list:
#   https://docs.coreweave.com/products/storage/object-storage/buckets/create-bucket
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/caios-keys.env"

# CAIOS primary endpoint (used from outside a cluster, e.g. your laptop/CI).
ENDPOINT_URL="https://cwobject.com"

SRC_BUCKET="${SRC_BUCKET:-}"
SRC_AZ="${SRC_AZ:-}"
DST_BUCKET="${DST_BUCKET:-}"
DST_AZ="${DST_AZ:-}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: aws CLI is not installed or not in PATH${NC}"
    exit 1
fi

# All four parameters are required — there is no universal default.
missing=""
[ -z "$SRC_BUCKET" ] && missing="$missing SRC_BUCKET"
[ -z "$SRC_AZ" ]     && missing="$missing SRC_AZ"
[ -z "$DST_BUCKET" ] && missing="$missing DST_BUCKET"
[ -z "$DST_AZ" ]     && missing="$missing DST_AZ"
if [ -n "$missing" ]; then
    echo -e "${RED}Error: missing required variable(s):${NC}${missing}"
    echo "Set them first, e.g.:"
    echo "  export SRC_BUCKET=my-source-bucket SRC_AZ=US-EAST-04A"
    echo "  export DST_BUCKET=my-dest-bucket   DST_AZ=US-WEST-01A"
    exit 1
fi

# Load the access key from caios-keys.env if not already in the environment.
if [ -z "${AWS_ACCESS_KEY_ID:-}" ] || [ -z "${AWS_SECRET_ACCESS_KEY:-}" ]; then
    if [ -f "$ENV_FILE" ]; then
        set -a; # shellcheck disable=SC1090
        source "$ENV_FILE"; set +a
    fi
fi
if [ -z "${AWS_ACCESS_KEY_ID:-}" ] || [ -z "${AWS_SECRET_ACCESS_KEY:-}" ]; then
    echo -e "${RED}Error: CAIOS credentials not found.${NC}"
    echo "Run ./setup-credentials.sh first, or export AWS_ACCESS_KEY_ID and"
    echo "AWS_SECRET_ACCESS_KEY, or create $ENV_FILE from the template."
    exit 1
fi

# CAIOS requires virtual-hosted-style addressing. The AWS CLI only reads this
# from a config file, so write a throwaway one scoped to this script.
AWS_CONFIG_FILE="$(mktemp)"
export AWS_CONFIG_FILE
cat > "$AWS_CONFIG_FILE" << 'EOF'
[default]
s3 =
    addressing_style = virtual
EOF
trap 'rm -f "$AWS_CONFIG_FILE"' EXIT

# create_bucket <name> <az>
create_bucket() {
    local bucket="$1" az="$2"
    echo -e "Creating ${YELLOW}${bucket}${NC} in ${YELLOW}${az}${NC}..."

    # Already exists and owned by us? head-bucket returns 0.
    if aws s3api head-bucket --bucket "$bucket" --region "$az" \
        --endpoint-url "$ENDPOINT_URL" &> /dev/null; then
        echo -e "${GREEN}✓ ${bucket} already exists — skipping${NC}"
        return 0
    fi

    aws s3api create-bucket \
        --bucket "$bucket" \
        --region "$az" \
        --create-bucket-configuration "LocationConstraint=${az}" \
        --endpoint-url "$ENDPOINT_URL"
    echo -e "${GREEN}✓ Created ${bucket}${NC}"
}

create_bucket "$SRC_BUCKET" "$SRC_AZ"
create_bucket "$DST_BUCKET" "$DST_AZ"

echo ""
echo -e "${GREEN}Done.${NC}"
echo "  source:      ${SRC_BUCKET}  (${SRC_AZ})"
echo "  destination: ${DST_BUCKET}  (${DST_AZ})"
echo ""
echo -e "${YELLOW}Note:${NC} new buckets can take ~1 minute to become listable due to DNS caching."
echo "If a follow-up command returns 'InvalidRegion ... Region does not match', wait and retry."
