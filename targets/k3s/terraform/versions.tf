terraform {
  required_version = ">= 1.15.0"

  backend "remote" {}

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }
}
