variable "kubernetes_version" {
  description = "Full AKS patch version verified by the approved technical preflight."
  type        = string

  validation {
    condition     = can(regex("^1\\.[0-9]{2}\\.[0-9]+$", var.kubernetes_version))
    error_message = "Kubernetes version must use a full version such as 1.35.5."
  }
}
