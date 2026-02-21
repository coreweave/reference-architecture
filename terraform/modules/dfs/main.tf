# CoreWeave DFS (Distributed File Storage) PVC – storage class shared-vast, ReadWriteMany
resource "kubernetes_manifest" "pvc" {
  count = var.create ? 1 : 0
  manifest = {
    apiVersion = "v1"
    kind       = "PersistentVolumeClaim"
    metadata = {
      name      = var.pvc_name
      namespace = var.namespace
    }
    spec = {
      accessModes      = ["ReadWriteMany"]
      storageClassName = "shared-vast"
      resources = {
        requests = {
          storage = var.size
        }
      }
    }
  }
}
