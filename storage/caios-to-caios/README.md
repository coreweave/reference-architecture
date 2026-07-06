# CAIOS to CAIOS Cross-Region Transfer

This solution copies data between two [CoreWeave AI Object Storage (CAIOS)](https://docs.coreweave.com/products/storage/object-storage/about)
buckets that live in **different regions / Availability Zones**, using the
[CoreWeave fork of `s5cmd`](https://github.com/coreweave/s5cmd) run as a
Kubernetes Job.

Unlike [`caios-to-dfs`](../caios-to-dfs/) (object storage → filesystem) or
[`gcs-caios-copy`](../gcs-caios-copy/) (Google Cloud Storage → CAIOS), both the
source and destination here are the *same* service — CAIOS. The "cross-region"
dimension lives entirely in each bucket's **`LocationConstraint`** (its
Availability Zone), not in the credentials or the endpoint.

## How CAIOS addressing works (read this first)

A few facts about CAIOS drive the whole design:

- **Buckets are AZ-scoped.** A bucket is pinned to one Availability Zone at
  creation time via `LocationConstraint` (for example `US-EAST-04A`). You cannot
  move a bucket between AZs — you create a second bucket in the target AZ and
  copy into it.
- **There is one global endpoint, not one-per-region.**
  - `https://cwobject.com` — the primary endpoint, used from **outside** a
    CoreWeave cluster (your laptop, CI, etc.). Requires TLS v1.3.
  - `http://cwlota.com` — the [LOTA](https://docs.coreweave.com/products/storage/object-storage/improving-performance/about-lota)
    endpoint, used from **inside** a CoreWeave cluster. LOTA caches **reads**.
  - CAIOS uses **virtual-hosted-style** addressing (`<bucket>.cwobject.com`), so
    the bucket name in the request routes to the correct AZ automatically.
- **One org access key reaches every bucket in the org, in every AZ.** Because
  the endpoint is global and access keys are organization-scoped, a single
  Access Key ID / Secret Key pair can read the source bucket and write the
  destination bucket regardless of which AZs they live in. You do **not** need a
  separate key per region.
- **Cross-region writes are supported but slower.** Per the
  [object storage best practices](https://docs.coreweave.com/products/storage/object-storage/improving-performance/best-practices#handle-cross-region-writes),
  CAIOS supports cross-region writes; LOTA only caches reads, so writing into a
  remote-AZ bucket incurs higher latency.
- **Bucket-to-bucket copy is server-side.** `s5cmd cp`/`sync` between two S3
  URLs issues S3 `CopyObject` calls, so the object bytes move **on the CAIOS
  backend between AZs** — they do not stream down to the pod and back up. This
  is exactly the method CoreWeave documents for
  [moving data across regions](https://docs.coreweave.com/support/storage/articles/how-do-i-move-data-across-regions).

Practical consequences for the design:

- The transfer pod is a lightweight **control plane** — it drives many
  concurrent `CopyObject` requests, but doesn't carry the data. Pod CPU/memory
  and node network are not the bottleneck, so there's **no need to shard across
  many nodes**; a single pod with a high worker count handles the whole bucket.
- Running it as a Job inside one of your CoreWeave clusters keeps the transfer
  in-network and easy to monitor and re-run — but because the copy is
  server-side, you could run the same `s5cmd` command from anywhere that has the
  credentials (including your laptop).
- `s5cmd` is the CoreWeave-recommended tool here: high default concurrency (256
  workers) and server-side copy make it faster than a stream-through approach.

## Prerequisites

- A CoreWeave organization with CAIOS enabled.
- CAIOS available in both the source and destination Availability Zones — see
  the [supported AZ list](https://docs.coreweave.com/products/storage/object-storage/buckets/create-bucket).
- A CoreWeave **API access token** *or* a kubeconfig for your org with
  `cwobject:createaccesskey` permission (used to mint the CAIOS access key).
- A CoreWeave Kubernetes (CKS) cluster in your org to run the transfer Job.
- Local tooling: `kubectl`, `curl`, `jq`, and the [AWS CLI](https://aws.amazon.com/cli/)
  (used to mint the key and create the AZ-pinned buckets). Optionally the
  [CoreWeave `s5cmd` fork](https://github.com/coreweave/s5cmd/releases) locally
  if you want to test the copy off-cluster before running the Job.

## Files

| File | Purpose |
|------|---------|
| `setup-credentials.sh` | Mints a CAIOS access key for your org (from a kubeconfig token) and writes `caios-keys.env`. |
| `create-buckets.sh` | Creates the source and destination buckets, each in its own AZ via `LocationConstraint`. Idempotent. |
| `caios-keys.env.template` | Template for the CAIOS Access Key ID / Secret Key. |
| `job.yaml.template` | Kubernetes Job that downloads the pinned CoreWeave `s5cmd` fork and runs the server-side `sync` from `src` → `dst`. |

## Setup

Every step is parameterized with environment variables so you can point it at
your own org, AZs, and bucket names. Set these once in your shell and the rest
of the commands pick them up.

### 1. Choose your parameters

```bash
# Source bucket and the AZ it lives in.
# Tip: if a cluster will run the Job, put the source in that cluster's AZ so
# reads are served from the local LOTA cache.
export SRC_BUCKET="<your-source-bucket>"
export SRC_AZ="<SOURCE-AZ>"        # e.g. US-EAST-04A

# Destination bucket and a different region's AZ.
export DST_BUCKET="<your-destination-bucket>"
export DST_AZ="<DEST-AZ>"          # e.g. US-WEST-01A
```

Pick AZs from the [list of zones that support AI Object Storage](https://docs.coreweave.com/products/storage/object-storage/buckets/create-bucket).

> **Bucket naming rules:** 3–63 chars, lowercase letters / numbers / hyphens
> only, globally unique, must start and end with a letter or number, and must
> **not** begin with `cw-`, `vip-`, or `log-stitcher-ch-` (these are reserved
> for CoreWeave).

### 2. Mint a CAIOS access key

The CAIOS access key is organization-scoped and works for both buckets in both
AZs. You can create one two ways:

**Option A — Cloud Console (no CLI):** Create an access key in the
[Cloud Console](https://console.coreweave.com/object-storage/access-keys), then
copy `caios-keys.env.template` to `caios-keys.env` and paste in the values.

**Option B — Script (from a kubeconfig):** If you have a kubeconfig for your org
with `cwobject:createaccesskey` permission:

```bash
# Point kubectl at your org's kubeconfig first, then:
./setup-credentials.sh
```

This calls the CoreWeave API, retrieves a fresh Access Key ID / Secret Key, and
writes them to `caios-keys.env` (mode `600`). **Treat this file like a password
— it is git-ignored by default.**

Load the keys into your shell for the next step:

```bash
set -a; source caios-keys.env; set +a
```

### 3. Create the two buckets

```bash
./create-buckets.sh
```

This creates `$SRC_BUCKET` in `$SRC_AZ` and `$DST_BUCKET` in `$DST_AZ` using the
AWS CLI against `https://cwobject.com` with virtual-hosted addressing. It is
idempotent — if a bucket already exists and you own it, it is left untouched.

> **Bucket creation delay:** When you create a bucket with an S3 client, it can
> take ~1 minute to become available due to DNS caching. If a follow-up command
> returns `InvalidRegion ... Region does not match`, wait a minute and retry.

### 4. (Optional) Verify access locally with s5cmd

If you installed the [CoreWeave `s5cmd` fork](https://github.com/coreweave/s5cmd/releases)
locally, confirm the key reaches both buckets before deploying the Job:

```bash
# Lists should succeed (empty is fine)
s5cmd --endpoint-url https://cwobject.com ls "s3://$SRC_BUCKET/"
s5cmd --endpoint-url https://cwobject.com ls "s3://$DST_BUCKET/"
```

You can also run the full copy directly from your laptop (it's server-side, so
it works from anywhere with the credentials):

```bash
s5cmd --endpoint-url https://cwobject.com \
      --numworkers 256 \
      sync "s3://$SRC_BUCKET/*" "s3://$DST_BUCKET/"
```

The Job below does the same thing inside your cluster.

## The transfer workload (Kubernetes Job)

With the key and buckets in place, the transfer is a single `s5cmd sync` running
as a Kubernetes Job in your CKS cluster. Because S3→S3 copy is **server-side**,
one pod with a high worker count copies the whole bucket — there's no sharding,
manifest, or multi-node fan-out.

The Job uses a stock `alpine` image and downloads the **pinned CoreWeave `s5cmd`
fork** release at startup (arch auto-detected for x86_64 / aarch64). The fork is
required: it defaults to virtual-host addressing for `cwobject.com` /
`cwlota.com`, which AI Object Storage needs — stock upstream `s5cmd` uses
path-style and won't work.

### 1. Create the namespace and credentials secret

```bash
kubectl create namespace data-migration

# Build the secret straight from caios-keys.env (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)
kubectl -n data-migration create secret generic caios-credentials \
  --from-env-file=caios-keys.env
```

### 2. Configure and deploy the Job

```bash
cp job.yaml.template job.yaml
```

Edit `job.yaml` and set:
- `<YOUR_SOURCE_BUCKET_NAME>` → your source bucket (`$SRC_BUCKET`)
- `<YOUR_DESTINATION_BUCKET_NAME>` → your destination bucket (`$DST_BUCKET`)
- (optional) `NUMWORKERS` / `CONCURRENCY` for your object-size mix
- (optional) `S5CMD_TAG` / `S5CMD_VER` to pin a different fork release

Then deploy:

```bash
kubectl -n data-migration apply -f job.yaml
```

### 3. Monitor

```bash
kubectl -n data-migration get job caios-xregion-copy
kubectl -n data-migration get pods
kubectl -n data-migration logs -l job-name=caios-xregion-copy -f
```

### 4. Verify completion

`s5cmd sync` only copies objects that are missing or changed at the destination,
so the Job is safely re-runnable — re-applying it resumes where it left off.
Compare the two buckets when it finishes:

```bash
# Object count + total size on each side (run locally, or with kubectl exec)
s5cmd --endpoint-url https://cwobject.com du "s3://$SRC_BUCKET/*"
s5cmd --endpoint-url https://cwobject.com du "s3://$DST_BUCKET/*"
```

### 5. Clean up

```bash
kubectl -n data-migration delete job caios-xregion-copy
kubectl -n data-migration delete secret caios-credentials
# Optionally: kubectl delete namespace data-migration
```

## Performance & tuning notes

- **`--numworkers`** (global worker pool, default 256) controls how many files
  copy concurrently. Raise it for **many small files**.
- **`--concurrency`** (parts per file, default 5) controls multipart parallelism
  for a **single large file**. Raise it (and lower `--numworkers`) for a few
  large objects.
- **Mixed workloads** — balance both (e.g. `--numworkers 64 --concurrency 8`).
- **Pod resources** — server-side copy keeps the pod light; the defaults
  (2 CPU / 4–8 Gi) are generous for the control-plane role. Increase only if you
  push `--numworkers` very high.
- See [Optimize s5cmd performance](https://docs.coreweave.com/products/storage/object-storage/migrate-data#optimize-s5cmd-performance).

> **Fallback — if server-side cross-AZ copy ever errors:** s5cmd S3→S3 copy is
> always server-side. In the unlikely event CAIOS rejects a cross-AZ
> `CopyObject`, switch to rclone with `--s3-no-server-side-copy`, which streams
> the data through the pod instead (see the [`caios-to-dfs`](../caios-to-dfs/)
> sibling for the rclone pattern).

## Security considerations

- `caios-keys.env` and any rendered `job.yaml` contain credentials and are
  git-ignored. Never commit them.
- `caios-keys.env` is written with `600` permissions; the Job reads credentials
  from a Kubernetes Secret, not from the image or args.
- The access key is organization-scoped — anyone holding it can read/write every
  bucket in the org. Rotate or delete it from the
  [Cloud Console](https://console.coreweave.com/object-storage/access-keys) when
  the transfer is complete.
