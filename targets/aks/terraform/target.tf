locals {
  aks_target = jsondecode(file("${path.root}/target.json"))
}
