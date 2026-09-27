locals {
  # Match the live resources: the resource group predates the northeurope
  # environment, and changing either value forces replacement.
  resource_group_location        = "westeurope"
  location                       = "northeurope"
  resource_group_name            = "halligalli-container-apps"
  container_app_environment_name = "halligalli-live-demo"
  container_app_name             = "halligalli-live-demo"

  # Cloudflare proxies play.halligalli.games, so the ingress admits only Cloudflare's edge.
  # Otherwise the default *.azurecontainerapps.io FQDN would bypass Cloudflare and let a client
  # write the X-Forwarded-For entry the API trusts as the client address.
  # Source: https://www.cloudflare.com/ips/ (ips-v4), fetched 2026-09-26. The Container Apps
  # ingress is IPv4-only, so Cloudflare reaches it over IPv4 and the IPv6 ranges are omitted.
  cloudflare_ipv4_ranges = [
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
  ]

  desired_state = jsondecode(file("${path.root}/desired-state.json"))

  web_repository   = try(local.desired_state.webImage.repository, "")
  web_digest       = try(local.desired_state.webImage.digest, "")
  api_repository   = try(local.desired_state.apiImage.repository, "")
  api_digest       = try(local.desired_state.apiImage.digest, "")
  redis_repository = try(local.desired_state.redisImage.repository, "")
  redis_digest     = try(local.desired_state.redisImage.digest, "")

  web_image   = "${local.web_repository}@${local.web_digest}"
  api_image   = "${local.api_repository}@${local.api_digest}"
  redis_image = "${local.redis_repository}@${local.redis_digest}"

  desired_state_images_are_deployable = alltrue([
    for image in [
      { repository = local.web_repository, digest = local.web_digest },
      { repository = local.api_repository, digest = local.api_digest },
      { repository = local.redis_repository, digest = local.redis_digest },
    ] :
    image.repository != "" &&
    can(regex("^sha256:[0-9a-f]{64}$", image.digest)) &&
    image.digest != "sha256:0000000000000000000000000000000000000000000000000000000000000000"
  ])
}

resource "azurerm_resource_group" "live_demo" {
  name     = local.resource_group_name
  location = local.resource_group_location
}

resource "azurerm_container_app_environment" "live_demo" {
  name                = local.container_app_environment_name
  location            = local.location
  resource_group_name = azurerm_resource_group.live_demo.name
}

resource "azurerm_container_app" "live_demo" {
  name                         = local.container_app_name
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

    dynamic "ip_security_restriction" {
      for_each = local.cloudflare_ipv4_ranges
      content {
        name             = "cloudflare-${ip_security_restriction.key}"
        description      = "Cloudflare edge"
        action           = "Allow"
        ip_address_range = ip_security_restriction.value
      }
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
      # Cloudflare appends the client, the platform ingress appends the Cloudflare edge, and the
      # Web nginx appends the ingress. The ingress admits only Cloudflare, so all three are trusted.
      env {
        name  = "HALLIGALLI_TRUSTED_PROXY_HOPS"
        value = "3"
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
      command = ["sh", "-c", "exec redis-server --save '' --appendonly no --maxmemory 180mb --maxmemory-policy noeviction"]

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
      condition     = try(local.desired_state.deploymentEnabled == true, false)
      error_message = "The checked-in Container Apps desired state must explicitly enable deployment."
    }

    precondition {
      condition     = local.desired_state_images_are_deployable
      error_message = "The checked-in Container Apps desired state must select complete, digest-pinned, non-placeholder Web, API, and Redis images."
    }
  }
}

output "live_demo_hostname" {
  value = azurerm_container_app.live_demo.ingress[0].fqdn
}
