variable "location" {
  type    = string
  default = "westeurope"
}

variable "resource_group_name" {
  type    = string
  default = "halligalli-container-apps"
}

variable "container_app_name" {
  type    = string
  default = "halligalli-live-demo"
}

variable "custom_domain_name" {
  type    = string
  default = "play.halligalli.games"
}

variable "environment_certificate_id" {
  type        = string
  description = "Existing Container Apps environment certificate for the approved custom domain."
}

variable "monthly_budget_target_usd" {
  type        = number
  default     = 25
  description = "Monthly operating budget target in USD; notification wiring is configured separately."

  validation {
    condition     = var.monthly_budget_target_usd == 25
    error_message = "The initial Live Demo monthly budget target must remain USD 25 until deliberately reviewed."
  }
}

variable "web_image" {
  type = string
}

variable "api_image" {
  type = string
}

variable "redis_image" {
  type = string
}
