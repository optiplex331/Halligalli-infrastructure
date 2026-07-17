resource "azurerm_kubernetes_cluster" "aks" {
  name                = local.aks_cluster_name
  location            = local.region
  resource_group_name = azurerm_resource_group.aks.name
  dns_prefix          = local.dns_prefix
  kubernetes_version  = var.kubernetes_version
  node_resource_group = local.node_resource_group_name
  sku_tier            = local.aks.management_tier

  oidc_issuer_enabled               = false
  role_based_access_control_enabled = true
  workload_identity_enabled         = false

  default_node_pool {
    name                 = local.aks.node_pool_name
    vm_size              = local.aks.node_vm_size
    node_count           = local.aks.node_count
    os_disk_size_gb      = local.aks.node_os_disk_size_gb
    max_pods             = local.aks.node_max_pods
    auto_scaling_enabled = false
    vnet_subnet_id       = azurerm_subnet.aks_system.id
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.aks_control_plane.id]
  }

  network_profile {
    network_plugin    = local.network.plugin
    network_policy    = local.network.policy
    load_balancer_sku = local.network.load_balancer_sku
    service_cidr      = local.network.service_cidr
    dns_service_ip    = local.network.dns_service_ip
  }

  tags = local.common_tags

  depends_on = [
    azurerm_role_assignment.aks_subnet_network_contributor,
  ]
}

check "terraform_stops_at_aks_boundary" {
  assert {
    condition     = !local.gitops.terraform_manages_kubernetes_apps && !local.gitops.terraform_manages_argocd_resources
    error_message = "Terraform must stop at the AKS boundary; Argo CD owns in-cluster desired state."
  }
}
