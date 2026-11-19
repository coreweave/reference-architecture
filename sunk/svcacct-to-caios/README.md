## Goal
Provide a way for sunk jobs to authenticate to caios buckets using short lived tokens

## Pre-Reqs
- `pod-identity-webhook` helm chart installed from https://charts.core-services.ingress.coreweave.com
- A bucket policy to allow your service account, and trust relationship for you CKS cluster's oidc issuer
  - The oidc issuer can be found with `kubectl get --raw /.well-known/openid-configuration | yq .issuer`

## Setup
1. Update the configmap with your bucket region and add it to `tenant-slurm`
2. Add the service account that will be attached to login and worker pods
3. Update your login and compute values with the changes noted in slurm-values.yaml
4. Your login pods and compute pods should roll when idle and pick up the changes