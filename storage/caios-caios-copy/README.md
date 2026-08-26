# CAIOS to CAIOS S3 Copy via Rclone

A CronJob that copies objects from one CAIOS bucket to another with [rclone](https://rclone.org/) using Workload Identity Federation for auth.

If you are able to use a single entry in `rclone.conf` (not going across regions for CAIOS), then rclone will use `CopyObject` which will run the copy server-side instead of buffering locally, thus being faster.

Across CAIOS regions, this has been tested to ~13GiB/s but might be able to be pushed a bit harder.


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
        "role/https://oidc.cks.coreweave.com/id/<ID>:system:serviceaccount:<NAMESPACE>:caios-to-caios-rclone"
    } 
  ]
}
```
