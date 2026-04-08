locals {
  oidc_issuer_hostpath = trimsuffix(replace(var.oidc_issuer_url, "https://", ""), "/")
  oidc_subject         = "system:serviceaccount:${var.namespace}:${var.service_account_name}"

  secret_names = {
    DB_USERNAME = "${var.secret_name_prefix}/db-username"
    DB_PASSWORD = "${var.secret_name_prefix}/db-password"
    API_TOKEN   = "${var.secret_name_prefix}/api-token"
  }
}

resource "aws_kms_key" "secrets" {
  description             = "KMS key for Secrets Manager entries used by the CoreWeave secrets reference architecture."
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_kms_alias" "secrets" {
  name          = var.kms_key_alias
  target_key_id = aws_kms_key.secrets.key_id
}

resource "aws_secretsmanager_secret" "app" {
  for_each = local.secret_names

  name       = each.value
  kms_key_id = aws_kms_key.secrets.arn
}

resource "aws_secretsmanager_secret_version" "app" {
  for_each = local.secret_names

  secret_id     = aws_secretsmanager_secret.app[each.key].id
  secret_string = var.secret_values[each.key]
}

data "aws_iam_policy_document" "assume_role_with_web_identity" {
  statement {
    effect = "Allow"

    actions = [
      "sts:AssumeRoleWithWebIdentity",
    ]

    principals {
      type = "Federated"
      identifiers = [
        var.oidc_provider_arn,
      ]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_issuer_hostpath}:sub"
      values   = [local.oidc_subject]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_issuer_hostpath}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eso_reader" {
  name               = var.role_name
  assume_role_policy = data.aws_iam_policy_document.assume_role_with_web_identity.json
}

data "aws_iam_policy_document" "read_secrets" {
  statement {
    sid    = "ReadReferencedSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetResourcePolicy",
      "secretsmanager:GetSecretValue",
      "secretsmanager:ListSecretVersionIds",
    ]
    resources = [for secret in aws_secretsmanager_secret.app : secret.arn]
  }

  statement {
    sid    = "DecryptSecretValues"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:DescribeKey",
    ]
    resources = [aws_kms_key.secrets.arn]
  }
}

resource "aws_iam_role_policy" "read_secrets" {
  name   = "${var.role_name}-policy"
  role   = aws_iam_role.eso_reader.id
  policy = data.aws_iam_policy_document.read_secrets.json
}
