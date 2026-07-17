locals {
  environment_name = "aks"
  short_name       = "aks"
  name_prefix      = "halligalli-${local.short_name}"

  resource_group_name      = coalesce(var.resource_group_name, "halligalli-boss-practice-${local.environment_name}-rg")
  aks_cluster_name         = coalesce(var.aks_cluster_name, "${local.name_prefix}-aks")
  node_resource_group_name = coalesce(var.node_resource_group_name, "${local.name_prefix}-nodes-rg")
  dns_prefix               = coalesce(var.dns_prefix, local.name_prefix)
  vnet_name                = "${local.name_prefix}-vnet"
  aks_subnet_name          = "aks-system"
  control_plane_identity   = "${local.name_prefix}-control-plane-mi"

  region = "westeurope"

  network = {
    plugin              = "azure"
    policy              = "azure"
    load_balancer_sku   = "standard"
    vnet_address_space  = ["10.42.0.0/16"]
    aks_subnet_prefixes = ["10.42.0.0/22"]
    service_cidr        = "10.43.0.0/16"
    dns_service_ip      = "10.43.0.10"
  }

  dns = {
    authority        = "Name.com"
    zone_name        = var.domain_name
    ingress_hostname = "${var.ingress_subdomain}.${var.domain_name}"
    public_url       = "https://${var.ingress_subdomain}.${var.domain_name}"
    apex_reserved    = var.domain_name
    azure_dns        = false
  }

  aks = {
    sku_name             = "Base"
    management_tier      = "Free"
    node_pool_name       = "system"
    node_count           = 2
    node_vm_size         = "Standard_D4ls_v6"
    node_os_disk_size_gb = 64
    node_max_pods        = 30
    node_pool_intent     = "two-node-system-validation"
  }

  gitops = {
    desired_state_path                 = "gitops/aks"
    reconciler                         = "Argo CD"
    terraform_manages_kubernetes_apps  = false
    terraform_manages_argocd_resources = false
    release_image_policy               = "digest-pinned GHCR Release Image"
    runtime_hostname                   = local.dns.ingress_hostname
  }

  lifecycle = {
    default_operation       = "plan"
    activation_requires     = "explicit local operation approval"
    intended_runtime        = "maintained AKS Deployment Target; no live workload is claimed outside an approved validation run"
    preserve_container_apps = false
    move_dns_in_phase_a     = false
    proof_destroy_required  = true
  }

  common_tags = {
    Application       = "Halligalli"
    Environment       = local.environment_name
    ManagedBy         = "Terraform"
    Repository        = "Halligalli-infrastructure"
    TerraformRoot     = "terraform/aks"
    Runtime           = "Paired FastAPI"
    PortfolioProof    = "true"
    CostProfile       = "bounded-two-node-aks-validation"
    Lifecycle         = "approved-create-validate-destroy"
    AKSSkuName        = local.aks.sku_name
    AKSManagementTier = local.aks.management_tier
  }
}
