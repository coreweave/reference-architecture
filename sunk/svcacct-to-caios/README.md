## Goal
Provide a way for sunk jobs to authenticate to caios buckets using short lived tokens. 
We also allow the same sunk job to authenticate to an AWS bucket using a different profile in the configmap.

## Pre-Reqs
- `pod-identity-webhook` helm chart installed from https://charts.core-services.ingress.coreweave.com
- A bucket policy to allow your service account, and trust relationship for you CKS cluster's oidc issuer
  - The oidc issuer can be found with `kubectl get --raw /.well-known/openid-configuration | yq .issuer`

## Setup
1. Update the configmap with your bucket region and add it to `tenant-slurm`
2. Add the service account that will be attached to login and worker pods
3. Update your login and compute values with the changes noted in slurm-values.yaml. Note that these values are truncated so just take what you need.
4. Your login pods and compute pods should roll when idle and pick up the changes.

## Usage
- By default auth to CoreWeave buckets will #JustWork due to the default profile in the configmap and the s6 script setting the env vars.
- To auth to an AWS bucket just set the profile with `export AWS_PROFILE=aws` when you want to use an AWS bucket. Most object storage libraries such as boto3 will have a similar method to set the profile as needed.
