resource "azurerm_resource_group" "live_demo" {
  name     = var.resource_group_name
  location = var.location
}

resource "azurerm_container_app_environment" "live_demo" {
  name                = "halligalli-live-demo"
  location            = azurerm_resource_group.live_demo.location
  resource_group_name = azurerm_resource_group.live_demo.name
}

resource "azurerm_container_app" "live_demo" {
  name                         = var.container_app_name
  container_app_environment_id = azurerm_container_app_environment.live_demo.id
  resource_group_name          = azurerm_resource_group.live_demo.name
  revision_mode                = "Multiple"

  ingress {
    external_enabled = true
    target_port      = 8080
    transport        = "auto"

    custom_domain {
      name                     = var.custom_domain_name
      certificate_binding_type = "SniEnabled"
      certificate_id           = var.environment_certificate_id
    }

    traffic_weight {
      revision_suffix = "bootstrap"
      percentage      = 100
    }
  }

  template {
    revision_suffix = "bootstrap"
    min_replicas    = 1
    max_replicas    = 1

    container {
      name   = "web"
      image  = var.web_image
      cpu    = 0.12
      memory = "0.25Gi"
      env {
        name  = "HALLIGALLI_API_ORIGIN"
        value = "http://localhost:8000"
      }
    }

    container {
      name   = "api"
      image  = var.api_image
      cpu    = 0.26
      memory = "0.5Gi"
      env {
        name  = "HALLIGALLI_REDIS_URL"
        value = "redis://localhost:6379/0"
      }
    }

    container {
      name    = "redis"
      image   = var.redis_image
      cpu     = 0.12
      memory  = "0.25Gi"
      command = ["redis-server", "--save", "", "--appendonly", "no"]
    }
  }

  lifecycle {
    ignore_changes = [ingress[0].traffic_weight]
  }
}

output "live_demo_hostname" {
  value = azurerm_container_app.live_demo.ingress[0].fqdn
}

output "monthly_budget_target_usd" {
  value       = var.monthly_budget_target_usd
  description = "Operating target only; Azure budget alerts require separately approved notification recipients."
}
