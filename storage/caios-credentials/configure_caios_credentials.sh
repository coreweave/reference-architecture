#!/bin/bash

# Script to create Kubernetes secret with access key and secret key
# Prerequisite: kubectl must be installed and configured to access the desired cluster
# User must have downloaded the kubeconfig file and it must be used by kubectl

# Goal - make it easier to set up your local CAIOS CoreWeave credentials
# by starting from only an admin KUBECONFIG file for a user with cwobject:createaccesskey permissions
set -e

# Hardcoded values
SECRET_NAME="caios-credentials"
API_ENDPOINT="https://api.coreweave.com/v1/cwobject/access-key"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Error: kubectl is not installed or not in PATH${NC}"
    exit 1
fi

# Check if curl and jq are installed
if ! command -v curl &> /dev/null; then
    echo -e "${RED}Error: curl is not installed or not in PATH${NC}"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo -e "${RED}Error: jq is not installed or not in PATH${NC}"
    echo "Install jq with: brew install jq"
    exit 1
fi

# Get the API token from kubeconfig
echo "Extracting API token from kubeconfig..."
API_ACCESS_TOKEN=$(kubectl config view --raw -o jsonpath='{.users[0].user.token}')

if [ -z "$API_ACCESS_TOKEN" ]; then
    echo -e "${RED}Error: Could not extract token from kubeconfig${NC}"
    exit 1
fi

echo "Token extracted successfully"

# Create JSON payload
JSON_PAYLOAD='{"durationSeconds": 0}'

# Make API call to get access key and secret key
echo "Requesting access credentials from CoreWeave API..."
RESPONSE=$(curl -s -X POST "$API_ENDPOINT" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_ACCESS_TOKEN" \
    -d "$JSON_PAYLOAD")

# Check if curl was successful
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: API request failed${NC}"
    exit 1
fi

# Parse the response and extract access key and secret key
ACCESS_KEY=$(echo "$RESPONSE" | jq -r '.accessKeyId')
SECRET_KEY=$(echo "$RESPONSE" | jq -r '.secretKey')


# Verify we got valid credentials
if [ -z "$ACCESS_KEY" ] || [ "$ACCESS_KEY" = "null" ]; then
    echo -e "${RED}Error: Failed to extract access key from API response${NC}"
    echo "Response: $RESPONSE"
    exit 1
fi

if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "null" ]; then
    echo -e "${RED}Error: Failed to extract secret key from API response${NC}"
    echo "Response: $RESPONSE"
    exit 1
fi

echo -e "${GREEN}✓ Credentials retrieved successfully${NC}"


# Create the directory if it doesn't exist
mkdir -p ~/.coreweave

# Check if files already exist
if [ -f ~/.coreweave/cw.credentials ] || [ -f ~/.coreweave/cw.config ]; then
    echo "Error: Coreweave configuration files already exist. Will not overwrite."
    [ -f ~/.coreweave/cw.credentials ] && echo "  - ~/.coreweave/cw.credentials exists"
    [ -f ~/.coreweave/cw.config ] && echo "  - ~/.coreweave/cw.config exists"
    exit 1
fi


# Create the credentials file
cat > ~/.coreweave/cw.credentials << EOF
[default]
aws_access_key_id = ${ACCESS_KEY}
aws_secret_access_key = ${SECRET_KEY}
output = json
[cw]
aws_access_key_id = ${ACCESS_KEY}
aws_secret_access_key = ${SECRET_KEY}
output = json
EOF

# Set appropriate permissions
chmod 600 ~/.coreweave/cw.credentials

# Create the config file
cat > ~/.coreweave/cw.config << EOF
[default]
endpoint_url = https://cwlota.com
s3 =
    addressing_style = virtual
[profile cw]
endpoint_url = https://cwobject.com
s3 =
    addressing_style = virtual
EOF

# Set appropriate permissions
chmod 600 ~/.coreweave/cw.config

echo "Credentials file created successfully at ~/.coreweave/cw.credentials"
echo "Config file created successfully at ~/.coreweave/cw.config"

echo "To use CoreWeave object storage on your laptop, execute these commands in your shell."
echo "You may also want to add them to your shell profile (~/.bashrc, ~/.zshrc, etc.):"
echo ""

echo export AWS_SHARED_CREDENTIALS_FILE=\"~/.coreweave/cw.credentials\"
echo export AWS_CONFIG_FILE=\"~/.coreweave/cw.config\"
echo export AWS_PROFILE=\"cw\"

echo "To use CoreWeave object storage from CoreWeave, copy them to your pod or SUNK home directory."
echo "Then set the environment variables to use the default profile."

echo export AWS_SHARED_CREDENTIALS_FILE=\"~/.coreweave/cw.credentials\"
echo export AWS_CONFIG_FILE=\"~/.coreweave/cw.config\"
echo export AWS_PROFILE=\"default\"

