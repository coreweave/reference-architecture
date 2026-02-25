# CKS NodePool via Kubernetes provider (CoreWeave has no Terraform nodepool resource).
# CRD: compute.coreweave.com/v1alpha1 NodePool
resource "kubernetes_manifest" "nodepool" {
  count = var.create ? 1 : 0
  manifest = {
    apiVersion = "compute.coreweave.com/v1alpha1"
    kind       = "NodePool"
    metadata = {
      name = var.name
    }
    spec = merge(
      {
        autoscaling  = var.autoscaling
        instanceType = var.instance_type
        maxNodes     = var.max_nodes
        minNodes     = var.min_nodes
        targetNodes  = var.target_nodes
      },
      length(var.node_labels) > 0 ? { nodeLabels = var.node_labels } : {},
      length(var.node_annotations) > 0 ? { nodeAnnotations = var.node_annotations } : {},
      length(var.node_taints) > 0 ? { nodeTaints = var.node_taints } : {}
    )
  }
}
