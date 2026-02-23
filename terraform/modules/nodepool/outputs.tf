output "nodepool_name" {
  value       = var.create ? var.name : null
  description = "NodePool name (null if not created)"
}
