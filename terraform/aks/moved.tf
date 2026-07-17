moved {
  from = azurerm_resource_group.production
  to   = azurerm_resource_group.aks
}

moved {
  from = azurerm_kubernetes_cluster.production
  to   = azurerm_kubernetes_cluster.aks
}
