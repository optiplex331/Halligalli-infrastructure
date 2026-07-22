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
