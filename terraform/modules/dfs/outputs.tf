output "pvc_name" {
  value       = var.create ? var.pvc_name : null
  description = "DFS PVC name (null if not created)"
}

output "namespace" {
  value       = var.create ? var.namespace : null
  description = "DFS PVC namespace (null if not created)"
}
