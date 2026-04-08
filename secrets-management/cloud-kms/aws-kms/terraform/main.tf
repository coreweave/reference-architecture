data "terraform_remote_state" "cks" {
  count = var.cks_remote_state_backend == null ? 0 : 1

  backend = var.cks_remote_state_backend
  config  = var.cks_remote_state_config
}

locals {
  effective_oidc_issuer_url = coalesce(
    var.oidc_issuer_url,
    try(data.terraform_remote_state.cks[0].outputs.cks_service_account_oidc_issuer_url, null)
  )

  oidc_issuer_hostpath = trimsuffix(replace(local.effective_oidc_issuer_url, "https://", ""), "/")
  oidc_subject         = "system:serviceaccount:${var.namespace}:${var.service_account_name}"
  effective_oidc_provider_arn = coalesce(
    var.oidc_provider_arn,
    try(aws_iam_openid_connect_provider.cks[0].arn, null)
  )

  secret_names = {
    DB_USERNAME = "${var.secret_name_prefix}/db-username"
    DB_PASSWORD = "${var.secret_name_prefix}/db-password"
    API_TOKEN   = "${var.secret_name_prefix}/api-token"
  }
}

check "oidc_issuer_url_present" {
  assert {
    condition     = local.effective_oidc_issuer_url != null && trim(local.effective_oidc_issuer_url) != ""
    error_message = "An OIDC issuer URL is required. Set oidc_issuer_url directly or configure cks_remote_state_* to read cks_service_account_oidc_issuer_url from your CKS terraform outputs."
  }
}

check "oidc_provider_present" {
  assert {
    condition = (
      var.create_oidc_provider ||
      (local.effective_oidc_provider_arn != null && trim(local.effective_oidc_provider_arn) != "")
    )
    error_message = "An AWS IAM OIDC provider ARN is required when create_oidc_provider=false. Set oidc_provider_arn or enable create_oidc_provider."
  }
}

data "tls_certificate" "oidc" {
  count = var.create_oidc_provider ? 1 : 0
  url   = local.effective_oidc_issuer_url
}

resource "aws_iam_openid_connect_provider" "cks" {
  count = var.create_oidc_provider ? 1 : 0

  url = local.effective_oidc_issuer_url

  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    data.tls_certificate.oidc[0].certificates[0].sha1_fingerprint,
  ]
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
        local.effective_oidc_provider_arn,
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
