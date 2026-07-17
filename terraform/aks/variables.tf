variable "domain_name" {
  description = "Domain used by manually managed DNS records during an approved AKS Validation Run."
  type        = string
  default     = "halligalli.games"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]*[a-z0-9]$", var.domain_name))
    error_message = "Domain name must be a lowercase DNS name."
  }
}

variable "ingress_subdomain" {
  description = "Subdomain intended for the same-origin AKS ingress entry."
  type        = string
  default     = "play"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.ingress_subdomain))
    error_message = "Ingress subdomain must be a lowercase DNS label."
  }
}

variable "resource_group_name" {
  description = "Optional resource group name override for the AKS Deployment Target."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.resource_group_name == null || can(regex("^[A-Za-z0-9_.()\\-]{1,90}$", var.resource_group_name))
    error_message = "Resource group name must be a valid Azure resource group name."
  }
}

variable "aks_cluster_name" {
  description = "Optional AKS cluster name override."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.aks_cluster_name == null || can(regex("^[A-Za-z0-9][A-Za-z0-9-]{1,61}[A-Za-z0-9]$", var.aks_cluster_name))
    error_message = "AKS cluster name must be 3-63 alphanumeric or hyphen characters."
  }
}

variable "node_resource_group_name" {
  description = "Optional AKS-managed node resource group name override."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.node_resource_group_name == null || can(regex("^[A-Za-z0-9_.()\\-]{1,90}$", var.node_resource_group_name))
    error_message = "Node resource group name must be a valid Azure resource group name."
  }
}

variable "dns_prefix" {
  description = "Optional DNS prefix for the AKS API server."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.dns_prefix == null || can(regex("^[a-z0-9][a-z0-9-]{0,52}[a-z0-9]$", var.dns_prefix))
    error_message = "AKS DNS prefix must be a lowercase DNS label up to 54 characters."
  }
}

variable "kubernetes_version" {
  description = "Optional target Kubernetes version selected during the approved validation preflight. This root does not model an in-place upgrade."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.kubernetes_version == null || can(regex("^1\\.[0-9]{2}\\.[0-9]+$", var.kubernetes_version))
    error_message = "Kubernetes version must use a full version such as 1.31.8, or null."
  }
}
