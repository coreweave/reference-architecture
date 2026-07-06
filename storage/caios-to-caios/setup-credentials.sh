#!/bin/bash
#
# Mint a CAIOS access key for the current organization and write it to
# caios-keys.env for use by create-buckets.sh and the rclone transfer.
#
# Prerequisites:
#   - kubectl configured against a kubeconfig for the org, for a user with
#     cwobject:createaccesskey permission.
#   - curl and jq installed.
#
# The resulting access key is organization-scoped: it can read and write every
# CAIOS bucket in the org, in every Availability Zone. You only need one.
#
# Alternative: create the key in the Cloud Console
# (https://console.coreweave.com/object-storage/access-keys), then copy
# caios-keys.env.template to caios-keys.env and paste in the values.
set -euo pipefail

API_ENDPOINT="https://api.coreweave.com/v1/cwobject/access-key"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/caios-keys.env"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

for cmd in kubectl curl jq; do
    if ! command -v "$cmd" &> /dev/null; then
        echo -e "${RED}Error: $cmd is not installed or not in PATH${NC}"
        [ "$cmd" = "jq" ] && echo "Install jq with: brew install jq"
        exit 1
    fi
done

if [ -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: $ENV_FILE already exists. Will not overwrite.${NC}"
    echo "Delete it first if you want to mint a new key."
    exit 1
fi

echo "Extracting API token from the current kubeconfig context..."
API_ACCESS_TOKEN="$(kubectl config view --raw -o jsonpath='{.users[0].user.token}')"
if [ -z "$API_ACCESS_TOKEN" ]; then
    echo -e "${RED}Error: Could not extract a token from kubeconfig.${NC}"
    echo "Make sure kubectl is pointed at the org's kubeconfig."
    exit 1
fi

echo "Requesting a CAIOS access key from the CoreWeave API..."
RESPONSE="$(curl -s -X POST "$API_ENDPOINT" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${API_ACCESS_TOKEN}" \
    -d '{"durationSeconds": 0}')"

ACCESS_KEY="$(echo "$RESPONSE" | jq -r '.accessKeyId')"
SECRET_KEY="$(echo "$RESPONSE" | jq -r '.secretKey')"

if [ -z "$ACCESS_KEY" ] || [ "$ACCESS_KEY" = "null" ] || \
   [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "null" ]; then
    echo -e "${RED}Error: Failed to obtain credentials from the API.${NC}"
    echo "Response: $RESPONSE"
    exit 1
fi

echo -e "${GREEN}✓ Access key retrieved successfully${NC}"

cat > "$ENV_FILE" << EOF
# CAIOS organization access key — minted by setup-credentials.sh
# Organization-scoped: works for every bucket in this org, in every AZ.
# Treat this file like a password. It is git-ignored.
AWS_ACCESS_KEY_ID=${ACCESS_KEY}
AWS_SECRET_ACCESS_KEY=${SECRET_KEY}
EOF
chmod 600 "$ENV_FILE"

echo -e "${GREEN}✓ Wrote ${ENV_FILE}${NC}"
echo ""
echo "Next steps:"
echo -e "  ${YELLOW}set -a; source ${ENV_FILE}; set +a${NC}    # load the key into your shell"
echo -e "  ${YELLOW}./create-buckets.sh${NC}                   # create the source + destination buckets"
