variable "cloudflare_account_id" {
  description = "Cloudflare account ID that owns the K3s Tunnel."
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for halligalli.games."
  type        = string
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token used only by approved local Terraform operations."
  type        = string
  sensitive   = true
}
