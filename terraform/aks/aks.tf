resource "azurerm_kubernetes_cluster" "aks" {
  name                = "halligalli-aks"
  location            = "westeurope"
  resource_group_name = azurerm_resource_group.aks.name
  dns_prefix          = "halligalli-aks"
  kubernetes_version  = var.kubernetes_version
  node_resource_group = "halligalli-aks-nodes-rg"
  sku_tier            = "Free"

  oidc_issuer_enabled               = false
  role_based_access_control_enabled = true
  workload_identity_enabled         = false

  default_node_pool {
    name                 = "system"
    vm_size              = "Standard_D4ls_v6"
    node_count           = 2
    os_disk_size_gb      = 64
    max_pods             = 30
    auto_scaling_enabled = false
    vnet_subnet_id       = azurerm_subnet.aks_system.id
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.aks_control_plane.id]
  }

  network_profile {
    network_plugin    = "azure"
    network_policy    = "azure"
    load_balancer_sku = "standard"
    service_cidr      = "10.43.0.0/16"
    dns_service_ip    = "10.43.0.10"
  }

  tags = azurerm_resource_group.aks.tags

  depends_on = [
    azurerm_role_assignment.aks_subnet_network_contributor,
  ]
}
