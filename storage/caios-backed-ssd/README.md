# CAIOS Dev Backup Demo

Fast `emptyDir` volumes on CoreWeave GPU nodes are fantastic for workloads 
that need low-latency storage, but **the data vanishes** whenever a pod is
rescheduled. 
This repo shows how to _persist_ the important parts of those volumes by
streaming them to **CoreWeave AI Object Storage (CAIOS)** in real time.

## How it works
0. In this example, we assume pods are development environments, which means 
each pod will be associated to a username (e.g., `jane`).
1. Using **emptyDir on local SSD** – fastest storage for `git`, `pip install`, etc.  
2. An **_init container_** restores the previous snapshot for the user from
   `s3://$BUCKET/$USERNAME/…` at pod start.  
3. A lightweight **`rclone` sidecar** continuously mirrors changes back to
   CAIOS every `$SYNC_INTERVAL` seconds.  
4. If the pod dies or moves, a new replica runs the same init container,
   pulling the last snapshot before the user even logs in.

CAIOS is S3‑compatible. You can use the global endpoint `https://cwobject.com` and
**virtual‑host style** addressing to connect to it.

Example `rclone` profile:
```
[caios]
type = s3
provider = Other
endpoint = https://cwobject.com
force_path_style = false
no_check_bucket = true
```

## Quick‑start (cluster admin)

```bash
git clone https://github.com/coreweave/reference-architecture.git
cd reference-architecture/storage/caios-backed-ssd

## Create the 'dev' namespace
kubectl apply -f manifests/00-namespace.yaml

cp .env.sample .env

## IMPORTANT
## Open the new .env file and edit values in .env

## Turn on allexport
set -a

source .env

envsubst < manifests/rclone.conf.template > manifests/rclone.conf
# Create rclone configuration secret in 'dev' namespace
kubectl -n dev create secret generic rclone-config \
  --from-file=rclone.conf=manifests/rclone.conf
```

### Provision a new developer environment
```bash
# Jane needs a box:
DEV_USERNAME=jane ./scripts/new-dev.sh | kubectl apply -f -
# Pod appears as dev-jane in namespace "dev".
```

## Tuning
- SYNC_TRANSFERS, SYNC_CHUNK_SIZE, --s3-upload-concurrency – adjust
depending on object sizes (see CoreWeave’s optimisation table).
- emptyDir.sizeLimit – set per‑user quota on node SSD.
- Swap the Deployment for a StatefulSet if you prefer stable pod names.
- Use local-storage provisioner for less reloading from CAIOS when a 
pod comes back up.

## Performance notes
- This sample is only backing up a `/workdir` directory now, but 
similar techniques can be applied to back up other directories as needed.
- The initial copy is configured assuming a large numbers of small files 
(--transfers 256).
- Performing a `git clone` operation of the 
[linux kernel](https://github.com/torvalds/linux) repo with default git 
settings takes several minutes, so restoring a directory with similar repos 
will also take several minutes. In our testing, restoring a fork of the 
linux kernel repo (13 GB) took just under 5 minutes.

## Security Notes
- Access keys live only in a namespaced Secret; the containers read them
via env vars. Rotate keys by replacing the secret.
- The sidecar uses `--s3-no-head` to reduce extra HEAD requests; omit if you
require per‑object integrity verification.

## Cleaning up
```bash
kubectl -n dev delete deployment dev-jane   # removes pod and deployment
# Optionally delete user data from CAIOS
rclone purge caios:dev-backups/jane
```
