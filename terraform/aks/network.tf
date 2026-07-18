resource "azurerm_resource_group" "aks" {
  name     = "halligalli-boss-practice-aks-rg"
  location = "westeurope"
  tags = {
    Application   = "Halligalli"
    Environment   = "aks"
    ManagedBy     = "Terraform"
    Repository    = "Halligalli-infrastructure"
    TerraformRoot = "terraform/aks"
  }
}

resource "azurerm_virtual_network" "aks" {
  name                = "halligalli-aks-vnet"
  resource_group_name = azurerm_resource_group.aks.name
  location            = "westeurope"
  address_space       = ["10.42.0.0/16"]
  tags                = azurerm_resource_group.aks.tags
}

resource "azurerm_subnet" "aks_system" {
  name                 = "aks-system"
  resource_group_name  = azurerm_resource_group.aks.name
  virtual_network_name = azurerm_virtual_network.aks.name
  address_prefixes     = ["10.42.0.0/22"]
}

# Azure CNI needs a pre-authorized control-plane identity for the existing node
# subnet. This is not Kubernetes Workload Identity or an OIDC federation path.
resource "azurerm_user_assigned_identity" "aks_control_plane" {
  name                = "halligalli-aks-control-plane-mi"
  resource_group_name = azurerm_resource_group.aks.name
  location            = "westeurope"
  tags                = azurerm_resource_group.aks.tags
}

resource "azurerm_role_assignment" "aks_subnet_network_contributor" {
  scope                = azurerm_subnet.aks_system.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_user_assigned_identity.aks_control_plane.principal_id
}
