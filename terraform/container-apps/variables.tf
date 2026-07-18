variable "location" {
  type    = string
  default = "northeurope"
}

variable "resource_group_location" {
  type        = string
  default     = "westeurope"
  description = "Metadata location for the existing resource group; runtime capacity is selected by location."
}

variable "resource_group_name" {
  type    = string
  default = "halligalli-container-apps"
}

variable "container_app_name" {
  type    = string
  default = "halligalli-live-demo"
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
