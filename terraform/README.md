# CoreWeave Reference Architecture – Terraform

Deploy CoreWeave infrastructure with Terraform: a **VPC**, **CKS (Kubernetes) cluster**, optional **Object Storage bucket**, **NodePool(s)**, and **DFS (Distributed File Storage)** PVCs—all from this code. Uses a single root with modules and a two-phase apply (VPC + cluster first, then NodePool and DFS after kubeconfig is set).

## What this creates

| Resource | Required? | Description |
|----------|-----------|-------------|
| **VPC** | Yes | CoreWeave VPC with host prefixes and named CIDR prefixes for CKS (pod, service, internal LB). |
| **CKS cluster** | Yes | CoreWeave Kubernetes Service cluster in the VPC. |
| **Object Storage bucket** | No | CoreWeave AI Object Storage (S3-compatible) bucket. Requires your user to be in an S3 policy that allows create/list. |
| **NodePool(s)** | No | One or more CKS node pools (via Kubernetes manifest). Created in **phase 2** after the cluster exists and you have kubeconfig. Use **nodepools** in tfvars for multiple NodePools. |
| **DFS PVC(s)** | No | One or more Distributed File Storage PVCs (`shared-vast`, ReadWriteMany) in the cluster. Created in **phase 2** with NodePool. Use **dfs_pvcs** in tfvars for multiple PVCs. |

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/downloads) >= 1.2
- [CoreWeave](https://console.coreweave.com/) account
- **CoreWeave API token** – [Create in Console → Tokens](https://console.coreweave.com/tokens)
- (Optional) For **Object Storage bucket**: your user must be added to an **S3 policy** in CoreWeave Console that allows `ListBuckets` and `CreateBucket`; otherwise bucket creation returns 403.
- (Optional) For **NodePool and DFS** (phase 2): **kubeconfig** for your CKS cluster. Download it from CoreWeave Console after the cluster is running; set `cks_kubeconfig_path` in `terraform.tfvars` before enabling `create_nodepool` or `create_dfs_pvc`.

## Quick start

### 1. Clone and copy variables

```bash
git clone <this-repo-url>
cd <repo-directory>
cp terraform.tfvars.example terraform.tfvars
```

### 2. Set your values in `terraform.tfvars`

Edit `terraform.tfvars` and replace placeholders:

- **zone** – e.g. `US-EAST-02A`
- **vpc_name** – your VPC name
- **vpc_prefixes** – CIDR blocks for pod, service, and internal LB; see [CoreWeave VPC CIDR docs](https://docs.coreweave.com/docs/products/networking/vpc/vpc-cidr) for sizing and examples (the example values in `terraform.tfvars.example` are valid to use as-is).
- **cluster_name** – your CKS cluster name (max 30 characters)
- Leave **create_nodepool** and **create_dfs_pvc** as `false` for the first run.

Do **not** commit `terraform.tfvars` if it contains your API token.

### 3. Set your API token

Use one of these (recommended: environment variable):

```bash
export TF_VAR_coreweave_api_token="<YOUR_COREWEAVE_API_TOKEN>"
```

Or add to `terraform.tfvars` (do not commit):

```hcl
coreweave_api_token = "<YOUR_COREWEAVE_API_TOKEN>"
```

### 4. Phase 1 – Create VPC and CKS cluster

```bash
terraform init
terraform plan    # review
terraform apply   # creates VPC + cluster (~45 min for cluster)
```

Optionally create an **Object Storage bucket** by setting `object_storage_bucket_name` (and zone/tags) in `terraform.tfvars` before apply. Your user must have S3 policy access as in Prerequisites.

### 5. Phase 2 – NodePool and DFS (optional)

After the cluster is **Running**:

1. **Download kubeconfig** for your cluster from [CoreWeave Console](https://console.coreweave.com/) (open the cluster → download kubeconfig).
2. In `terraform.tfvars` set **cks_kubeconfig_path** to the path of the downloaded file (e.g. `"~/.kube/config"` or `"/path/to/cks-kubeconfig.yaml"`).
3. Set **create_nodepool = true** and/or **create_dfs_pvc = true** if you want them.
4. Apply again:

```bash
terraform apply
```

Terraform will create the NodePool(s) and/or DFS PVC(s) in the cluster. If you see errors like `no such host`, the kubeconfig is pointing at an old or wrong cluster; download a fresh kubeconfig for the current cluster.

**Multiple NodePools:** To create more than one NodePool, set **nodepools** in `terraform.tfvars` to a map (key = NodePool name, value = `{ instance_type, target_nodes, autoscaling, min_nodes, max_nodes, node_labels, node_annotations, node_taints }`). See `terraform.tfvars.example` (Option B). If **nodepools** is empty, the single-NodePool vars (**nodepool_name**, **nodepool_instance_type**, etc.) are used.

**Multiple DFS PVCs:** To create more than one DFS PVC in the same cluster, set **dfs_pvcs** in `terraform.tfvars` to a map (key = PVC name, value = `{ namespace, size }`). See `terraform.tfvars.example` (Option B). If **dfs_pvcs** is empty, the single-PVC vars (**dfs_pvc_name**, **dfs_pvc_namespace**, **dfs_pvc_size**) are used.

## Step-by-step (detailed)

| Step | Action |
|------|--------|
| 1 | Clone repo, `cp terraform.tfvars.example terraform.tfvars`. |
| 2 | Edit `terraform.tfvars`: set zone, vpc_name, cluster_name; keep create_nodepool and create_dfs_pvc **false**. |
| 3 | Set `TF_VAR_coreweave_api_token` (or coreweave_api_token in tfvars). Do not commit tfvars if it has the token. |
| 4 | (Optional) To create a bucket: set object_storage_bucket_name (and zone/tags). Ensure your user has S3 policy access. |
| 5 | Run `terraform init`, then `terraform plan` and `terraform apply`. Wait for cluster to be ready. |
| 6 | Download kubeconfig for the new cluster from CoreWeave Console. |
| 7 | In terraform.tfvars set cks_kubeconfig_path and set create_nodepool = true and/or create_dfs_pvc = true. |
| 8 | Run `terraform apply` again to create NodePool(s) and/or DFS PVC(s). |

## Repository structure

All resources are organized as **modules**. The root `main.tf` wires them together.

```
.
├── README.md
├── .gitignore
├── .terraform.lock.hcl       # Committed for reproducible provider versions
├── terraform.tfvars.example  # Copy to terraform.tfvars and fill in your values
├── providers.tf              # CoreWeave + Kubernetes providers, token variable
├── main.tf                   # Calls all modules (network, cks, object_storage, nodepool, dfs)
├── variables.tf              # Root variables (passed into modules)
├── outputs.tf                # Outputs from each module
└── modules/
    ├── network/              # VPC (coreweave_networking_vpc)
    │   ├── main.tf
    │   ├── variables.tf
    │   ├── outputs.tf
    │   └── versions.tf
    ├── cks/                  # CKS cluster (coreweave_cks_cluster)
    │   ├── main.tf
    │   ├── variables.tf
    │   ├── outputs.tf
    │   └── versions.tf
    ├── object_storage/       # Optional AI Object Storage bucket
    │   ├── main.tf
    │   ├── variables.tf
    │   ├── outputs.tf
    │   └── versions.tf
    ├── nodepool/             # Optional CKS NodePool (kubernetes_manifest)
    │   ├── main.tf
    │   ├── variables.tf
    │   ├── outputs.tf
    │   └── versions.tf
    └── dfs/                  # Optional DFS PVC (shared-vast, kubernetes_manifest)
        ├── main.tf
        ├── variables.tf
        ├── outputs.tf
        └── versions.tf
```

- **terraform.tfvars** is not committed; create it from `terraform.tfvars.example`.
- **State files** (`*.tfstate`) are not committed; use a [remote backend](https://developer.hashicorp.com/terraform/language/settings/backends/configuration) in production if needed.

### Migrating from older layout (root-level object_storage, nodepool, dfs)

If you previously had `object_storage.tf`, `nodepool.tf`, or `dfs.tf` at root and are updating to this module layout, Terraform will plan to destroy and recreate those resources unless you move state. To migrate state into the new modules (no destroy/recreate), run once after pulling:

```bash
# Only if you had existing bucket/nodepool/dfs at root and see plan destroy/recreate
terraform state mv 'coreweave_object_storage_bucket.main[0]' 'module.object_storage.coreweave_object_storage_bucket.main[0]' 2>/dev/null || true
terraform state mv 'kubernetes_manifest.nodepool_example[0]' 'module.nodepool["example-nodepool"].kubernetes_manifest.nodepool' 2>/dev/null || true
terraform state mv 'kubernetes_manifest.dfs_pvc[0]' 'module.dfs["dfs-shared"].kubernetes_manifest.pvc' 2>/dev/null || true
```

Omit any line that fails (resource not in state). Then run `terraform plan` again; it should show no changes for those resources.

## Object Storage bucket – S3 policy requirement

To create a bucket, your **user** (or the token’s principal) must be added to an **S3 policy** in CoreWeave Console that allows:

- `ListBuckets`
- `CreateBucket`

Without this, bucket creation fails with **403 AccessDenied**. Add your user to the appropriate Object Storage (S3) policy in Console, then use the same API token when running Terraform.

## Outputs

After apply, Terraform outputs include:

- **vpc_id** – Created VPC ID (from `module.network`)
- **cks_cluster_id**, **cks_cluster_name**, **cks_api_server_endpoint**, **cks_status** (from `module.cks`)
- **object_storage_bucket_name** – If a bucket was created (from `module.object_storage`)
- **nodepools** – Map of created NodePool names: key → nodepool_name (from `module.nodepool`; empty if create_nodepool is false)
- **dfs_pvcs** – Map of created DFS PVCs: name → { pvc_name, namespace } (from `module.dfs`; empty if create_dfs_pvc is false)

## Links

- [CoreWeave Cloud Console](https://console.coreweave.com/)
- [CoreWeave Terraform Provider](https://registry.terraform.io/providers/coreweave/coreweave/latest/docs)
- [CKS documentation](https://docs.coreweave.com/products/cks/clusters/introduction)
- [Object Storage – Create access tokens](https://docs.coreweave.com/products/storage/object-storage/auth-access/create-access-tokens)
- [DFS – Create volumes](https://docs.coreweave.com/products/storage/distributed-file-storage/create-volumes)
