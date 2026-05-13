locals {
  cks_pod_cidr_name          = var.vpc_prefixes[0].name
  cks_service_cidr_name      = var.vpc_prefixes[1].name
  cks_internal_lb_cidr_names = toset([for i in range(2, length(var.vpc_prefixes)) : var.vpc_prefixes[i].name])
  effective_oidc_issuer_url  = module.cks.service_account_oidc_issuer_url
  oidc_issuer_hostpath       = trimsuffix(replace(local.effective_oidc_issuer_url, "https://", ""), "/")
  oidc_subject               = "system:serviceaccount:${var.namespace}:${var.service_account_name}"
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

check "oidc_provider_present" {
  assert {
    condition = (
      var.create_oidc_provider ||
      (local.effective_oidc_provider_arn != null && trimspace(local.effective_oidc_provider_arn) != "")
    )
    error_message = "An AWS IAM OIDC provider ARN is required when create_oidc_provider=false. Set oidc_provider_arn or enable create_oidc_provider."
  }
}

module "network" {
  source = "../../../../terraform/modules/network"

  name          = var.vpc_name
  zone          = var.zone
  vpc_prefixes  = var.vpc_prefixes
  host_prefixes = var.host_prefixes
}

module "cks" {
  source = "../../../../terraform/modules/cks"

  cluster_name           = var.cluster_name
  kubernetes_version     = var.kubernetes_version
  zone                   = module.network.vpc_zone
  vpc_id                 = module.network.vpc_id
  public                 = var.cks_public
  pod_cidr_name          = local.cks_pod_cidr_name
  service_cidr_name      = local.cks_service_cidr_name
  internal_lb_cidr_names = local.cks_internal_lb_cidr_names
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
