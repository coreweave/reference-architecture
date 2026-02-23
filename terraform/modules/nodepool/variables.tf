variable "create" {
  type        = bool
  description = "Create the NodePool. Set to false when cluster is missing or kubeconfig points at a deleted cluster."
  default     = true
}

variable "name" {
  type        = string
  description = "NodePool metadata name"
  default     = "example-nodepool"
}

variable "instance_type" {
  type        = string
  description = "CKS instance type (e.g. gd-8xh100ib-i128)"
  default     = "gd-8xh100ib-i128"
}

variable "target_nodes" {
  type        = number
  description = "Desired number of nodes"
  default     = 2
}

variable "autoscaling" {
  type        = bool
  description = "Enable autoscaling"
  default     = false
}

variable "min_nodes" {
  type        = number
  description = "Min nodes when autoscaling"
  default     = 0
}

variable "max_nodes" {
  type        = number
  description = "Max nodes when autoscaling"
  default     = 0
}

variable "node_labels" {
  type        = map(string)
  description = "Labels applied to nodes"
  default     = {}
}

variable "node_annotations" {
  type        = map(string)
  description = "Annotations applied to nodes"
  default     = {}
}

variable "node_taints" {
  type = list(object({
    key    = string
    value  = string
    effect = string
  }))
  description = "Taints applied to nodes"
  default     = []
}
