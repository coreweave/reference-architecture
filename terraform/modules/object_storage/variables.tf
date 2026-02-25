variable "bucket_name" {
  type        = string
  description = "Object storage bucket name (globally unique; must not start with cw- or vip-). Set to null to skip creation."
  default     = null
}

variable "zone" {
  type        = string
  description = "Zone for the bucket (e.g. US-EAST-02A)"
}

variable "tags" {
  type        = map(string)
  description = "Tags to assign to the bucket"
  default     = {}
}
