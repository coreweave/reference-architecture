# CoreWeave Reference Architecture - Terraform

Deploy CoreWeave infrastructure with Terraform: a **VPC**, **CKS (Kubernetes) cluster**, optional **Object Storage bucket** with **access policies**, **NodePool(s)**, and **DFS (Distributed File Storage)** PVCs-all from this code. Uses a single root with modules and a two-phase apply (VPC + cluster first, then NodePool and DFS after kubeconfig is set).

## What this creates

| Resource | Required? | Description |
|----------|-----------|-------------|
| **VPC** | Yes | CoreWeave VPC with host prefixes and named CIDR prefixes for CKS (pod, service, internal LB). |
| **CKS cluster** | Yes | CoreWeave Kubernetes Service cluster in the VPC. Supports OIDC configuration for external IdPs. |
| **Object Storage org access policy** | No | Organization-wide access policy for AI Object Storage. At least one must exist before creating buckets. |
| **Object Storage bucket** | No | CoreWeave AI Object Storage (S3-compatible) bucket. |
| **Object Storage bucket policy** | No | Per-bucket S3-compatible access policy for fine-grained control. |
| **NodePool(s)** | No | One or more CKS node pools (via Kubernetes manifest). Created in **phase 2** after the cluster exists and you have kubeconfig. |
| **DFS PVC(s)** | No | One or more Distributed File Storage PVCs (`shared-vast`, ReadWriteMany) in the cluster. Created in **phase 2** with NodePool. |

## Prerequisites

- [Terraform](https://developer.hashicorp.com/terraform/downloads) >= 1.2
- [CoreWeave](https://console.coreweave.com/) account
- **CoreWeave API token** - [Create in Console -> Tokens](https://console.coreweave.com/tokens)
- (Optional) For **Object Storage**: set up an org access policy (via Terraform or Console) before creating buckets.
- (Optional) For **OIDC Workload Identity Federation**: create a WIF configuration in [Console -> Organization -> IAM -> Workload Federation](https://console.coreweave.com/organization/iam/workload-federation#oidc).
- (Optional) For **NodePool and DFS** (phase 2): **kubeconfig** for your CKS cluster.

## Quick start

### 1. Clone and copy variables

```bash
git clone <this-repo-url>
cd <repo-directory>
cp terraform.tfvars.example terraform.tfvars
```

### 2. Set your values in `terraform.tfvars`

Edit `terraform.tfvars` and replace placeholders:

- **zone** - e.g. `US-EAST-02A`
- **vpc_name** - your VPC name
- **vpc_prefixes** - CIDR blocks for pod, service, and internal LB; see [CoreWeave VPC CIDR docs](https://docs.coreweave.com/docs/products/networking/vpc/vpc-cidr) for sizing and examples (the example values in `terraform.tfvars.example` are valid to use as-is).
- **cluster_name** - your CKS cluster name (max 30 characters)
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

### 4. Phase 1 - Create VPC, CKS cluster, and Object Storage

```bash
terraform init
terraform plan    # review
terraform apply   # creates VPC + cluster (~45 min for cluster)
```

Optionally create **Object Storage** resources by setting the relevant variables in `terraform.tfvars`:
- `object_storage_org_access_policies` - organization-wide access policies (at least one required before bucket creation)
- `object_storage_bucket_name` - bucket name
- `object_storage_bucket_policy_statements` - per-bucket fine-grained access control

### 5. Phase 2 - NodePool and DFS (optional)

After the cluster is **Running**:

1. **Download kubeconfig** for your cluster from [CoreWeave Console](https://console.coreweave.com/).
2. In `terraform.tfvars` set **cks_kubeconfig_path** to the downloaded file path.
3. Set **create_nodepool = true** and/or **create_dfs_pvc = true**.
4. Apply again:

```bash
terraform apply
```

## Object Storage access policies

The CoreWeave Terraform provider supports two levels of Object Storage access policies. The `object_storage_org_access_policies` variable is a **map** (key = policy name), so you can create multiple policies for different concerns.

### Open access (single policy)

A single policy granting full S3 and Object Storage API access to every principal in the organization. Suitable for dev/test environments or single-team setups where all users share the same level of access:

```hcl
object_storage_org_access_policies = {
  "open-access" = {
    statements = [
      {
        name       = "allow-all-principals-full-access"
        effect     = "Allow"
        actions    = ["s3:*", "cwobject:*"]
        resources  = ["*"]
        principals = ["*"]
      }
    ]
  }
}
```

### Scoped access (multiple policies)

Separate policies for different access patterns - named principals, least-privilege actions, independently manageable and auditable:

```hcl
object_storage_org_access_policies = {
  # Policy 1: Admin users get full control
  "admin-access" = {
    statements = [
      {
        name       = "allow-admin-full-access"
        effect     = "Allow"
        actions    = ["s3:*", "cwobject:*"]
        resources  = ["*"]
        principals = ["admin@example.com", "platform-team@example.com"]
      }
    ]
  }

  # Policy 2: OIDC workload identity - scoped access for automated workloads
  "oidc-wif" = {
    statements = [
      {
        name       = "allow-oidc-key-creation"
        effect     = "Allow"
        actions    = ["cwobject:CreateAccessKeyFromOIDC"]
        resources  = ["*"]
        principals = ["role/https://idp.example.com:svc-data-ingest"]
      },
      {
        name       = "allow-s3-rw-training-bucket"
        effect     = "Allow"
        actions    = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"]
        resources  = ["training-data", "training-data/*"]
        principals = ["role/https://idp.example.com:svc-data-ingest"]
      }
    ]
  }
}
```

### Bucket access policy

Bucket access policies add fine-grained, S3-compatible access control for a single bucket. They are evaluated **after** organization access policies. Managed via `object_storage_bucket_policy_statements`.

```hcl
object_storage_bucket_policy_statements = [
  {
    sid    = "allow-read-oidc-role"
    effect = "Allow"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = ["arn:aws:s3:::my-bucket", "arn:aws:s3:::my-bucket/*"]
    principals = {
      "CW" = ["arn:aws:iam::<org-id>:role/https://idp.example.com:svc-reader"]
    }
  }
]
```

**Key difference:** Organization policies use short-form principals (e.g. `role/https://idp.example.com:sub`), while bucket policies use full ARNs (e.g. `arn:aws:iam::<org-id>:role/https://idp.example.com:sub`).

## OIDC Workload Identity Federation for Object Storage

For production use cases, OIDC Workload Identity Federation eliminates static API keys by exchanging short-lived JWT tokens from your identity provider for temporary Object Storage credentials.

> **What Terraform manages vs. what's manual:**
> - **Terraform manages:** Organization and bucket access policies that authorize OIDC-derived roles (steps 2-3 below)
> - **Manual (Console):** The WIF configuration that tells CoreWeave how to validate your IdP's tokens (step 1 below). There is no Terraform resource for WIF configurations today.
> - **Manual (workload):** Client-side environment variables that tell the AWS SDK where to exchange tokens (step 3 below)
>
> You will need your IdP's issuer URL and the subject identifier for your workloads before writing the Terraform policy.

### How it works

1. Your workload obtains an OIDC token from your identity provider (IdP)
2. The token is sent to CoreWeave's WIF endpoint
3. CoreWeave validates the token and returns temporary Access Key / Secret Key credentials
4. Credentials expire automatically; the AWS SDK handles refresh transparently

The derived role identity is: `role/<ISSUER_URL>:<SUBJECT>`

### Setup

#### Step 1: Create WIF configuration in Console

Navigate to [Console -> Organization -> IAM -> Workload Federation](https://console.coreweave.com/organization/iam/workload-federation#oidc) and create an OIDC configuration with:
- **Issuer URL**: Your IdP's URL (e.g. `https://your-domain.okta.com`)
- **Client ID (Audience)**: The value tokens must contain in their `aud` claim

#### Step 2: Create org access policy via Terraform

Grant `cwobject:CreateAccessKeyFromOIDC` to your OIDC-derived role, plus any S3 permissions. This can be its own policy or combined with others:

```hcl
object_storage_org_access_policies = {
  "oidc-wif" = {
    statements = [
      {
        name       = "allow-oidc-key-creation"
        effect     = "Allow"
        actions    = ["cwobject:CreateAccessKeyFromOIDC"]
        resources  = ["*"]
        principals = ["role/https://idp.example.com:svc-data-ingest"]
      },
      {
        name       = "allow-s3-rw"
        effect     = "Allow"
        actions    = ["s3:Get*", "s3:List*", "s3:Put*", "s3:DeleteObject"]
        resources  = ["my-bucket", "my-bucket/*"]
        principals = ["role/https://idp.example.com:svc-data-ingest"]
      }
    ]
  }
}
```

#### Step 3: Configure workloads

Set these environment variables (requires AWS CLI >= 2.33.2 or boto3 >= 1.42.5):

```bash
export AWS_CONTAINER_CREDENTIALS_FULL_URI=https://api.coreweave.com/v1/cwobject/temporary-credentials/oidc/<ORG_ID>
export AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE=/path/to/jwt-token

aws configure set s3.addressing_style virtual
export AWS_REGION="US-EAST-02A"
export AWS_ENDPOINT_URL_S3="https://cwobject.com"

# Test
aws s3 ls
```

### Using CKS service account tokens

CKS clusters expose an OIDC issuer URL for Kubernetes service account tokens (output as `cks_service_account_oidc_issuer_url`). You can use this as the issuer when creating the WIF configuration in Console, allowing CKS workloads to access Object Storage without any static credentials:

1. Create the CKS cluster and note the `cks_service_account_oidc_issuer_url` output
2. Create a WIF configuration in Console using that URL as the issuer
3. The role becomes: `role/<cks_service_account_oidc_issuer_url>:system:serviceaccount:<namespace>:<sa-name>`
4. Grant that role access in your org access policy

This is the recommended approach for CKS workloads accessing Object Storage.

## Step-by-step (detailed)

| Step | Action |
|------|--------|
| 1 | Clone repo, `cp terraform.tfvars.example terraform.tfvars`. |
| 2 | Edit `terraform.tfvars`: set zone, vpc_name, cluster_name; keep create_nodepool and create_dfs_pvc **false**. |
| 3 | Set `TF_VAR_coreweave_api_token` (or coreweave_api_token in tfvars). Do not commit tfvars if it has the token. |
| 4 | (Optional) Set object_storage_org_access_policies for org-wide access control (easy setup or production). |
| 5 | (Optional) Set object_storage_bucket_name (and zone/tags) to create a bucket. |
| 6 | (Optional) Set object_storage_bucket_policy_statements for per-bucket access control. |
| 7 | Run `terraform init`, then `terraform plan` and `terraform apply`. Wait for cluster to be ready. |
| 8 | (Optional, for OIDC WIF) Note the cks_service_account_oidc_issuer_url output. Create a WIF config in Console. |
| 9 | Download kubeconfig for the new cluster from CoreWeave Console. |
| 10 | In terraform.tfvars set cks_kubeconfig_path and set create_nodepool = true and/or create_dfs_pvc = true. |
| 11 | Run `terraform apply` again to create NodePool(s) and/or DFS PVC(s). |

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
    ├── object_storage/       # Optional AI Object Storage bucket + policies
    │   ├── main.tf           # Bucket, org access policy, bucket policy
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

## Outputs

After apply, Terraform outputs include:

- **vpc_id** - Created VPC ID (from `module.network`)
- **cks_cluster_id**, **cks_cluster_name**, **cks_api_server_endpoint**, **cks_status** (from `module.cks`)
- **cks_service_account_oidc_issuer_url** - OIDC issuer URL for CKS service account tokens (use for WIF setup)
- **object_storage_bucket_name** - If a bucket was created (from `module.object_storage`)
- **object_storage_org_access_policy_names** - Map of created org access policy names
- **object_storage_bucket_policy_json** - If a bucket policy was applied
- **nodepools** - Map of created NodePool names (from `module.nodepool`)
- **dfs_pvcs** - Map of created DFS PVCs (from `module.dfs`)

## Links

- [CoreWeave Cloud Console](https://console.coreweave.com/)
- [CoreWeave Terraform Provider](https://registry.terraform.io/providers/coreweave/coreweave/latest/docs)
- [CKS documentation](https://docs.coreweave.com/products/cks/clusters/introduction)
- [Object Storage - Access policies](https://docs.coreweave.com/platform/terraform/resources/object_storage_organization_access_policy)
- [Object Storage - Bucket policies](https://docs.coreweave.com/platform/terraform/resources/object_storage_bucket_policy)
- [Workload Identity Federation with OIDC](https://docs.coreweave.com/products/storage/object-storage/auth-access/workload-identity-federation/use-oidc-tokens)
- [DFS - Create volumes](https://docs.coreweave.com/products/storage/distributed-file-storage/create-volumes)
