locals {
  desired_state = jsondecode(file("${path.root}/../../deployment/container-apps/desired-state.json"))

  release_version  = try(local.desired_state.releaseVersion, "")
  release_commit   = try(local.desired_state.releaseCommit, "")
  web_repository   = try(local.desired_state.webImage.repository, "")
  web_digest       = try(local.desired_state.webImage.digest, "")
  api_repository   = try(local.desired_state.apiImage.repository, "")
  api_digest       = try(local.desired_state.apiImage.digest, "")
  redis_repository = try(local.desired_state.redisImage.repository, "")
  redis_digest     = try(local.desired_state.redisImage.digest, "")

  web_image   = "${local.web_repository}@${local.web_digest}"
  api_image   = "${local.api_repository}@${local.api_digest}"
  redis_image = "${local.redis_repository}@${local.redis_digest}"

  desired_state_is_complete = alltrue([
    try(local.desired_state.schemaVersion == 1, false),
    try(local.desired_state.target == "container-apps", false),
    try(local.desired_state.deploymentEnabled == true, false),
    can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+$", local.release_version)),
    can(regex("^[0-9a-f]{40}$", local.release_commit)),
    local.web_repository != "",
    can(regex("^sha256:[0-9a-f]{64}$", local.web_digest)),
    local.api_repository != "",
    can(regex("^sha256:[0-9a-f]{64}$", local.api_digest)),
    local.redis_repository != "",
    can(regex("^sha256:[0-9a-f]{64}$", local.redis_digest)),
  ])
}

resource "azurerm_resource_group" "live_demo" {
  name     = var.resource_group_name
  location = var.resource_group_location
}

resource "azurerm_container_app_environment" "live_demo" {
  name                = "halligalli-live-demo"
  location            = var.location
  resource_group_name = azurerm_resource_group.live_demo.name
}

resource "azurerm_container_app" "live_demo" {
  name                         = var.container_app_name
  container_app_environment_id = azurerm_container_app_environment.live_demo.id
  resource_group_name          = azurerm_resource_group.live_demo.name
  revision_mode                = "Single"

  ingress {
    external_enabled = true
    target_port      = 8080
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 1

    container {
      name   = "web"
      image  = local.web_image
      cpu    = 0.12
      memory = "0.25Gi"
      env {
        name  = "HALLIGALLI_API_ORIGIN"
        value = "http://localhost:8000"
      }

      startup_probe {
        transport               = "HTTP"
        port                    = 8080
        path                    = "/"
        interval_seconds        = 5
        timeout                 = 2
        failure_count_threshold = 30
      }

      readiness_probe {
        transport               = "HTTP"
        port                    = 8080
        path                    = "/"
        interval_seconds        = 5
        timeout                 = 2
        failure_count_threshold = 3
        success_count_threshold = 1
      }
    }

    container {
      name   = "api"
      image  = local.api_image
      cpu    = 0.26
      memory = "0.5Gi"
      env {
        name  = "HALLIGALLI_REDIS_URL"
        value = "redis://localhost:6379/0"
      }

      startup_probe {
        transport               = "TCP"
        port                    = 8000
        interval_seconds        = 5
        timeout                 = 2
        failure_count_threshold = 30
      }

      readiness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/internal/ready"
        interval_seconds        = 5
        timeout                 = 2
        failure_count_threshold = 3
        success_count_threshold = 1
      }
    }

    container {
      name    = "redis"
      image   = local.redis_image
      cpu     = 0.12
      memory  = "0.25Gi"
      command = ["sh", "-c", "exec redis-server --save '' --appendonly no"]

      startup_probe {
        transport               = "TCP"
        port                    = 6379
        interval_seconds        = 2
        timeout                 = 1
        failure_count_threshold = 30
      }

      readiness_probe {
        transport               = "TCP"
        port                    = 6379
        interval_seconds        = 5
        timeout                 = 1
        failure_count_threshold = 3
        success_count_threshold = 1
      }
    }
  }

  lifecycle {
    precondition {
      condition     = local.desired_state_is_complete
      error_message = "The checked-in Container Apps desired state must enable schemaVersion 1 for target container-apps and select one complete digest-pinned Web/API/Redis release pair."
    }
  }
}

output "live_demo_hostname" {
  value = azurerm_container_app.live_demo.ingress[0].fqdn
}

output "monthly_budget_target_usd" {
  value       = var.monthly_budget_target_usd
  description = "Operating target only; Azure budget alerts require separately approved notification recipients."
}
