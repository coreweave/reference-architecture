# AWS KMS + Secrets Manager Tutorial

This tutorial provisions a disposable CoreWeave VPC and CKS cluster, creates AWS Secrets Manager secrets encrypted with AWS KMS, and verifies that External Secrets Operator syncs them into Kubernetes.

## Prerequisites

- CoreWeave account permissions to create a VPC and CKS cluster.
- A CoreWeave API token exported as `TF_VAR_coreweave_api_token`.
- AWS credentials available to Terraform, for example through `AWS_PROFILE`, with permissions to create IAM roles and policies, an IAM OIDC provider, KMS keys, and Secrets Manager secrets.
- Terraform `>= 1.5`, `kubectl`, `helm`, and `aws`.
- Access to CoreWeave Console to download kubeconfig for the new CKS cluster.
- Schedulable CKS node capacity for ESO and the demo app. If the cluster does not get capacity automatically, create a NodePool after the cluster is ready.

## 1. Configure Terraform

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

- Set `zone`, `vpc_name`, and `cluster_name`.
- Set `aws_region`.
- Replace `secret_values`.
- Keep `create_oidc_provider = true` unless your AWS account already has an IAM OIDC provider for this CKS issuer.

Set credentials:

```bash
export TF_VAR_coreweave_api_token="<COREWEAVE_API_TOKEN>"
export AWS_PROFILE="<AWS_PROFILE>"
```

## 2. Provision

```bash
terraform init
terraform plan
terraform apply
terraform output
```

Record these outputs:

- `cks_cluster_name`
- `eso_role_arn`
- `secret_names`

## 3. Connect To CKS

Download kubeconfig for `cks_cluster_name` from CoreWeave Console, then point `kubectl` at it:

```bash
export KUBECONFIG="/path/to/downloaded/kubeconfig"
kubectl get nodes
```

If there are no schedulable nodes, apply the example CPU NodePool before continuing:

```bash
kubectl apply -f ../manifests/cpu-nodepool.yaml
kubectl get nodepool cpu
kubectl wait --for=condition=Ready nodes --all --timeout=10m
```

Edit `manifests/cpu-nodepool.yaml` if you need a different `instanceType` or `targetNodes`.

## 4. Install ESO

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update
helm install external-secrets external-secrets/external-secrets \
  --namespace external-secrets \
  --create-namespace
kubectl rollout status deployment/external-secrets -n external-secrets
```

## 5. Update Manifests

Edit `../manifests/10-service-account.yaml`:

- Set `metadata.annotations["eks.amazonaws.com/role-arn"]` to `eso_role_arn`.

Edit `../manifests/20-secret-store.yaml`:

- Set `spec.provider.aws.region` to `aws_region`.

If you changed `secret_name_prefix`, update remote keys in `../manifests/30-external-secret.yaml` to match `secret_names`.

## 6. Apply Manifests

```bash
kubectl apply -f ../manifests/00-namespace.yaml
kubectl apply -f ../manifests/10-service-account.yaml
kubectl apply -f ../manifests/20-secret-store.yaml
kubectl apply -f ../manifests/30-external-secret.yaml
kubectl apply -f ../manifests/40-demo-app.yaml
```

## 7. Verify

```bash
kubectl get secretstore,externalsecret -n secrets-aws
kubectl describe externalsecret app-secrets -n secrets-aws
kubectl get secret app-runtime-secrets -n secrets-aws
kubectl rollout status deployment/secrets-demo -n secrets-aws
kubectl logs deployment/secrets-demo -n secrets-aws
```

The demo logs should show:

```text
DB_USERNAME loaded
DB_PASSWORD loaded
API_TOKEN loaded
```

## 8. Test Rotation

```bash
aws secretsmanager put-secret-value \
  --secret-id ra-demo/db-password \
  --secret-string "rotated-password-$(date +%s)"
```

Wait at least one ESO refresh interval, then verify the Kubernetes Secret changed:

```bash
kubectl get secret app-runtime-secrets -n secrets-aws -o yaml
```

## 9. Clean Up

```bash
kubectl delete -f ../manifests/40-demo-app.yaml --ignore-not-found
kubectl delete -f ../manifests/30-external-secret.yaml --ignore-not-found
kubectl delete -f ../manifests/20-secret-store.yaml --ignore-not-found
kubectl delete -f ../manifests/10-service-account.yaml --ignore-not-found
kubectl delete -f ../manifests/00-namespace.yaml --ignore-not-found
terraform destroy
```
