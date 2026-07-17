resource "azurerm_resource_group" "aks" {
  name     = local.resource_group_name
  location = local.region
  tags     = local.common_tags
}

resource "azurerm_virtual_network" "aks" {
  name                = local.vnet_name
  resource_group_name = azurerm_resource_group.aks.name
  location            = local.region
  address_space       = local.network.vnet_address_space
  tags                = local.common_tags
}

resource "azurerm_subnet" "aks_system" {
  name                 = local.aks_subnet_name
  resource_group_name  = azurerm_resource_group.aks.name
  virtual_network_name = azurerm_virtual_network.aks.name
  address_prefixes     = local.network.aks_subnet_prefixes
}

# Azure CNI needs a pre-authorized control-plane identity for the existing node
# subnet. This is not Kubernetes Workload Identity or an OIDC federation path.
resource "azurerm_user_assigned_identity" "aks_control_plane" {
  name                = local.control_plane_identity
  resource_group_name = azurerm_resource_group.aks.name
  location            = local.region
  tags                = local.common_tags
}

resource "azurerm_role_assignment" "aks_subnet_network_contributor" {
  scope                = azurerm_subnet.aks_system.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_user_assigned_identity.aks_control_plane.principal_id
}
