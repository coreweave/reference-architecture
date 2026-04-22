# Cloud KMS Secret References

These references use cloud-native secret managers with customer-managed encryption keys:

- AWS: AWS Secrets Manager + AWS KMS
- GCP: Secret Manager + Cloud KMS (CMEK)

Both references use External Secrets Operator (ESO) to sync provider secrets into Kubernetes `Secret` objects for workloads.

## Key Security Properties

- No static AWS access keys or GCP service account key files are required for ESO.
- CKS workload identity is federated into each cloud provider for short-lived credentials.
- Secret values remain in provider-managed secret managers, encrypted by KMS keys.
- Terraform can source the CKS OIDC issuer URL automatically from this repo's CKS stack output (`cks_service_account_oidc_issuer_url`).

## Provider References

- AWS: [`aws-kms/`](./aws-kms/README.md)
- GCP: [`gcp-kms/`](./gcp-kms/README.md)
