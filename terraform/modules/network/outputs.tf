output "vpc_id" {
  value       = coreweave_networking_vpc.main.id
  description = "VPC ID for use by CKS or other resources"
}

output "vpc_zone" {
  value       = coreweave_networking_vpc.main.zone
  description = "VPC zone; use for CKS cluster and other resources that must be in the same zone"
}

output "name" {
  value       = coreweave_networking_vpc.main.name
  description = "VPC name"
}
