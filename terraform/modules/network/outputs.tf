output "vpc_id" {
  value       = coreweave_networking_vpc.main.id
  description = "VPC ID for use by CKS or other resources"
}

output "name" {
  value       = coreweave_networking_vpc.main.name
  description = "VPC name"
}
