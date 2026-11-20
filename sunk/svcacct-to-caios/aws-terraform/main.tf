locals {
  cks_oidc_issuer = replace(data.coreweave_cks_cluster.default.service_account_oidc_issuer_url, "https://", "")
  bucket_arn      = "arn:aws:s3:::${var.bucket_name}"
}

data "coreweave_cks_cluster" "default" {
  id = var.cluster_id
}

resource "aws_iam_openid_connect_provider" "cks" {
  url            = "https://${local.cks_oidc_issuer}"
  client_id_list = [var.audience]
}

data "aws_iam_policy_document" "assume" {
  statement {
    sid     = "AllowSlurmIdentityWebIdentity"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.cks.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.cks_oidc_issuer}:sub"
      values   = ["system:serviceaccount:${var.namespace}:${var.service_account}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.cks_oidc_issuer}:aud"
      values   = [var.audience]
    }
  }
}

resource "aws_iam_role" "slurm_identity" {
  name               = var.role_name
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_s3_bucket" "sunk" {
  count = var.create_bucket ? 1 : 0

  bucket = var.bucket_name
}

resource "aws_s3_bucket_public_access_block" "sunk" {
  count = var.create_bucket ? 1 : 0

  bucket = aws_s3_bucket.sunk[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "sunk_s3" {
  statement {
    sid       = "BucketList"
    effect    = "Allow"
    actions   = ["s3:GetBucketLocation", "s3:ListBucket", "s3:ListBucketMultipartUploads"]
    resources = [local.bucket_arn]
  }

  statement {
    sid    = "ObjectReadWrite"
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:ListMultipartUploadParts",
      "s3:PutObject",
    ]
    resources = ["${local.bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "sunk_s3" {
  name   = "${var.role_name}-s3"
  role   = aws_iam_role.slurm_identity.id
  policy = data.aws_iam_policy_document.sunk_s3.json
}
