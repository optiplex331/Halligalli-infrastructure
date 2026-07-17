"""Static contracts for the two-node AKS Deployment Target Terraform root."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TERRAFORM_ROOT = REPO_ROOT / "terraform" / "aks"


def terraform_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in TERRAFORM_ROOT.glob("*.tf"))


class AksGuardrailsTest(unittest.TestCase):
    def test_clean_snapshot_has_no_legacy_state_moves(self) -> None:
        self.assertFalse((TERRAFORM_ROOT / "moved.tf").exists())

    def test_locks_the_two_node_base_free_pool_shape(self) -> None:
        aks = (TERRAFORM_ROOT / "aks.tf").read_text(encoding="utf-8")
        locals_source = (TERRAFORM_ROOT / "locals.tf").read_text(encoding="utf-8")

        self.assertRegex(locals_source, r'management_tier\s+= "Free"')
        self.assertRegex(locals_source, r'node_pool_name\s+= "system"')
        self.assertRegex(locals_source, r'node_vm_size\s+= "Standard_D4ls_v6"')
        self.assertRegex(locals_source, r'node_count\s+= 2')
        self.assertRegex(locals_source, r'node_os_disk_size_gb\s+= 64')
        self.assertRegex(locals_source, r'node_max_pods\s+= 30')
        self.assertRegex(locals_source, r'aks_subnet_prefixes\s+= \["10.42.0.0/22"\]')
        for setting in (
            "local.aks.management_tier",
            "local.aks.node_pool_name",
            "local.aks.node_vm_size",
            "local.aks.node_count",
            "local.aks.node_os_disk_size_gb",
            "local.aks.node_max_pods",
            "local.network.plugin",
        ):
            self.assertIn(setting, aks)

    def test_removes_disallowed_platform_features(self) -> None:
        aks = (TERRAFORM_ROOT / "aks.tf").read_text(encoding="utf-8")
        source = terraform_source()

        self.assertIn("oidc_issuer_enabled               = false", aks)
        self.assertIn("workload_identity_enabled         = false", aks)
        self.assertIn("auto_scaling_enabled = false", aks)
        self.assertNotIn("oms_agent", source)
        self.assertNotIn("azurerm_log_analytics_workspace", source)
        self.assertNotIn("azurerm_kubernetes_cluster_node_pool", source)
        self.assertNotIn("zones =", aks)
        self.assertNotIn("priority =", aks)
        self.assertNotIn("upgrade_settings", source)
        self.assertNotIn("temporary_name_for_rotation", source)

    def test_keeps_terraform_outside_the_cluster_boundary(self) -> None:
        source = terraform_source()

        self.assertIn('check "terraform_stops_at_aks_boundary"', source)
        self.assertNotRegex(source, r'resource\s+"(?:kubernetes|helm|argocd)_')


if __name__ == "__main__":
    unittest.main()
