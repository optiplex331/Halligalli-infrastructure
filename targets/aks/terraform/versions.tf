terraform {
  required_version = ">= 1.15.0"

  backend "remote" {}

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}
