#!/bin/bash
# Marimo container startup script
# This script is executed before starting the Marimo server

set -e

echo "[$(date)] Starting container initialization..."

# Install system packages
echo "[$(date)] Installing system packages..."
apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    iputils-ping \
    net-tools \
    curl \
    wget \
    dnsutils \
    traceroute \
    awscli \
    kubectl
rm -rf /var/lib/apt/lists/*

# Install s5cmd (CoreWeave fork)
echo "[$(date)] Installing s5cmd..."
wget -q https://github.com/coreweave/s5cmd/releases/download/v2.3.0-acb67716/s5cmd_2.3.0-acb67716_Linux-64bit.tar.gz -O /tmp/s5cmd.tar.gz
tar xzf /tmp/s5cmd.tar.gz -C /tmp
chmod +x /tmp/s5cmd
mv /tmp/s5cmd /usr/local/bin/
rm /tmp/s5cmd.tar.gz

# Setup SSH
echo "[$(date)] Setting up SSH..."
mkdir -p /root/.ssh /root/.kube
chmod 700 /root/.ssh

if [ -f /secrets/ssh/id_rsa ]; then
    cp /secrets/ssh/id_rsa /root/.ssh/id_rsa
    chmod 600 /root/.ssh/id_rsa
    echo "[$(date)] SSH key installed"
fi

if [ -f /secrets/kubeconfig/config ]; then
    cp /secrets/kubeconfig/config /root/.kube/config
    chmod 600 /root/.kube/config
    echo "[$(date)] Kubeconfig installed"
fi

# SSH config - disable host key checking
cat > /root/.ssh/config << 'EOF'
Host *
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
  ServerAliveInterval 60
  ServerAliveCountMax 3
EOF
chmod 600 /root/.ssh/config

# Setup kubectl alias
echo "alias k='kubectl'" >> /root/.bashrc
ln -sf /usr/bin/kubectl /usr/local/bin/k

# Copy notebooks from ConfigMap to persistent storage
echo "[$(date)] Syncing notebooks..."
mkdir -p /home/marimo/notebooks/ailabs

# Remove any broken symlinks first
find /home/marimo/notebooks -maxdepth 1 -type l -name "*.py" -delete 2>/dev/null || true
find /home/marimo/notebooks/ailabs -maxdepth 1 -type l -name "*.py" -delete 2>/dev/null || true

# Copy notebooks (dereference symlinks from ConfigMap)
cp -L /notebooks-source/*.py /home/marimo/notebooks/ 2>/dev/null || true
cp -L /notebooks-source-ailabs/*.py /home/marimo/notebooks/ailabs/ 2>/dev/null || true

# Construct SSH host from components
export CW_AILABS_SSH_HOST="${CW_AILABS_SUNK_USER}@sunk.${CW_AILABS_CLUSTER_DOMAIN}"
echo "[$(date)] SSH host: $CW_AILABS_SSH_HOST"

# Sync benchmarks to remote login node
echo "[$(date)] Syncing benchmarks to remote login node..."
REMOTE_BENCHMARKS_DIR="/mnt/data/ailabs/benchmarks"

# Create remote benchmarks directory structure
ssh $CW_AILABS_SSH_HOST "mkdir -p $REMOTE_BENCHMARKS_DIR/nccl $REMOTE_BENCHMARKS_DIR/storage/object $REMOTE_BENCHMARKS_DIR/storage/dfs $REMOTE_BENCHMARKS_DIR/network" 2>/dev/null || echo "[$(date)] Warning: Could not create remote benchmarks directory"

# Copy local benchmark files to remote (preserving directory structure)
if [ -d /benchmarks-source ]; then
    echo "[$(date)] Copying benchmark files to remote..."
    # Copy each subdirectory's contents
    for subdir in nccl storage/object storage/dfs network; do
        if [ -d "/benchmarks-source/$subdir" ] && [ "$(ls -A /benchmarks-source/$subdir 2>/dev/null)" ]; then
            scp -r /benchmarks-source/$subdir/* "$CW_AILABS_SSH_HOST:$REMOTE_BENCHMARKS_DIR/$subdir/" 2>/dev/null || \
                echo "[$(date)] Warning: Could not copy $subdir files"
        fi
    done
    echo "[$(date)] Benchmark files copied successfully"
fi

# Clone/update nccl-tests repository on remote
echo "[$(date)] Setting up NCCL tests from GitHub..."
ssh $CW_AILABS_SSH_HOST "
    NCCL_DIR=$REMOTE_BENCHMARKS_DIR/nccl/nccl-tests
    if [ -d \"\$NCCL_DIR/.git\" ]; then
        echo 'Updating existing nccl-tests repository...'
        cd \$NCCL_DIR && git pull --ff-only 2>/dev/null || echo 'Warning: Could not update nccl-tests'
    else
        echo 'Cloning nccl-tests repository...'
        rm -rf \$NCCL_DIR
        git clone https://github.com/coreweave/nccl-tests.git \$NCCL_DIR 2>/dev/null || echo 'Warning: Could not clone nccl-tests'
    fi
" 2>/dev/null || echo "[$(date)] Warning: Could not setup NCCL tests on remote"

echo "[$(date)] Benchmarks sync complete."

# Credentials TTL - auto-expire and cleanup
if [ -n "$CREDENTIALS_TTL" ] && [ "$CREDENTIALS_TTL" -gt 0 ] 2>/dev/null; then
    echo "[$(date)] Credentials TTL set to ${CREDENTIALS_TTL}s"
    (
        sleep $CREDENTIALS_TTL
        echo "[$(date)] Credentials TTL expired after ${CREDENTIALS_TTL}s - cleaning up..."
        
        # Delete Kubernetes secrets (while we still have kubeconfig)
        kubectl delete secret ssh-key kubeconfig api-access-token aws-credentials --ignore-not-found=true 2>/dev/null || true
        
        # Delete local credential files
        rm -f /root/.ssh/id_rsa /root/.kube/config
        
        echo "[$(date)] Secrets removed. Terminating pod to clear in-memory credentials..."
        kill 1
    ) &
fi

echo "[$(date)] Initialization complete. Starting Marimo..."

# Start Marimo server
exec marimo edit --host 0.0.0.0 --port 2718 --token-password "$MARIMO_TOKEN"
