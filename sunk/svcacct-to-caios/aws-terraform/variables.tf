variable "org_id" {
  description = "The 6 character CoreWeave org ID"
  type        = string
}

variable "cluster_id" {
  description = "The CoreWeave CKS cluster ID, e.g. 3f393060-f8dd-4833-96b7-756e37c43223."
  type        = string
}

variable "bucket_name" {
  description = "Bucket name to give access to the sunk user."
  type        = string
}

variable "create_bucket" {
  description = "If the bucket should be created here."
  type        = bool
  default     = false
}

variable "role_name" {
  description = "Name of the IAM role the Slurm ServiceAccount assumes."
  type        = string
  default     = "sunk-identity"
}

variable "audience" {
  description = "Audience the federating pod's projected ServiceAccount token is minted for. Must match the projected token; AWS STS uses sts.amazonaws.com."
  type        = string
  default     = "sts.amazonaws.com"
}

variable "namespace" {
  description = "Namespace of the ServiceAccount that assumes this role."
  type        = string
  default     = "tenant-slurm"
}

variable "service_account" {
  description = "Name of the ServiceAccount that assumes this role."
  type        = string
  default     = "slurm-identity"
}

variable "aws_region" {
  description = "AWS region for the OIDC provider, IAM role and KMS keys."
  type        = string
}

variable "aws_profile" {
  description = "AWS shared-config profile the provider uses. Empty string uses the default credential chain (AWS_PROFILE / env / instance role)."
  type        = string
  default     = ""
}
