output "aks_cluster" {
  description = "Resource-derived AKS values for local operation after explicit approval."
  value = {
    name               = azurerm_kubernetes_cluster.aks.name
    resource_group     = azurerm_resource_group.aks.name
    kubernetes_version = azurerm_kubernetes_cluster.aks.kubernetes_version
    credential_command = "az aks get-credentials --resource-group ${azurerm_resource_group.aks.name} --name ${azurerm_kubernetes_cluster.aks.name} --overwrite-existing"
  }
}
