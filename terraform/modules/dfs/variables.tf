variable "create" {
  type        = bool
  description = "Create the DFS PVC. Set to true after cluster exists and kubeconfig is set."
  default     = false
}

variable "pvc_name" {
  type        = string
  description = "Name of the DFS PersistentVolumeClaim"
}

variable "namespace" {
  type        = string
  description = "Kubernetes namespace for the DFS PVC"
  default     = "default"
}

variable "size" {
  type        = string
  description = "Storage size (e.g. 100Gi, 1Ti)"
}
