# AWS to CAIOS S3 Copy via Rclone

A CronJob that copies objects from an AWS S3 bucket to a CoreWeave CAIOS bucket with [rclone](https://rclone.org/). AWS access uses IRSA (`sts:AssumeRoleWithWebIdentity`); CAIOS credentials come from the CAIOS sidecar.

## AWS IAM setup

Get the CKS cluster OIDC issuer:

```bash
kubectl get --raw /.well-known/openid-configuration | jq -r '.issuer'
```

CKS returns `https://oidc.cks.coreweave.com/id/<ID>`. Register that URL once per cluster under IAM > Identity Providers > OpenID Connect, with audience `sts.amazonaws.com`.

Create the role. In the trust policy, `<OIDC-ISSUER>` is the issuer URL with the `https://` prefix stripped:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Federated": "arn:aws:iam::<AWS-ACCOUNT-ID>:oidc-provider/<OIDC-ISSUER>" },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "<OIDC-ISSUER>:sub": "system:serviceaccount:<NAMESPACE>:aws-to-caios-rclone",
        "<OIDC-ISSUER>:aud": "sts.amazonaws.com"
      }
    }
  }]
}
```

```bash
aws iam create-role --role-name aws-to-caios-rclone \
  --assume-role-policy-document file://trust-policy.json
```

For read access to every bucket in the account, attach the managed policy:

```bash
aws iam attach-role-policy --role-name aws-to-caios-rclone \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess
```

## CKS Worklead Identity Federation Setup

For access to every bucket in the account, add the policy:

```json
{
  "name": "PodIdentity",
  "version": "v1alpha1",
  "statements": [
    {
      "name": "caios-access",
      "effect": "Allow",
      "actions": [
        "s3:*",
        "cwobject:CreateAccessKey",
        "cwobject:CreateAccessKeyOIDC",
      ],
      "resources": [
        "*"
      ],
      "principals": 
        "role/https://oidc.cks.coreweave.com/id/<ID>:system:serviceaccount:<NAMESPACE>:aws-to-caios-rclone"
    } 
  ]
}
```
