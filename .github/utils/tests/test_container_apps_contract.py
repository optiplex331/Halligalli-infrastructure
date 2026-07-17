"""Static and behavioral contracts for the Live Demo Environment."""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".github" / "utils"))

from container_apps_revision import (  # noqa: E402
    ContainerAppsRevisionError,
    render_candidate,
    validate_desired_state,
)


class ContainerAppsContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = json.loads((REPO_ROOT / "deployment/container-apps/desired-state.json").read_text())

    def test_desired_state_is_a_safe_non_deployable_bootstrap_placeholder(self) -> None:
        self.assertFalse(self.state["deploymentEnabled"])
        with self.assertRaisesRegex(ContainerAppsRevisionError, "bootstrap placeholder"):
            validate_desired_state(self.state)

    def test_promoted_desired_state_is_target_scoped_and_digest_pinned(self) -> None:
        self.state["deploymentEnabled"] = True
        release = validate_desired_state(self.state)
        self.assertEqual(release["version"], "0.7.2")
        self.assertTrue(release["web_image"].startswith("ghcr.io/"))
        self.assertIn("@sha256:", release["api_image"])

    def test_candidate_has_three_localhost_coupled_containers_and_fixed_scale(self) -> None:
        self.state["deploymentEnabled"] = True
        candidate = render_candidate(self.state, "r42-23cb9f6")
        template = candidate["properties"]["template"]
        self.assertEqual([item["name"] for item in template["containers"]], ["web", "api", "redis"])
        self.assertEqual(template["scale"], {"minReplicas": 1, "maxReplicas": 1})
        self.assertEqual([item["resources"]["cpu"] for item in template["containers"]], [0.12, 0.26, 0.12])
        self.assertEqual(sum(item["resources"]["cpu"] for item in template["containers"]), 0.5)
        self.assertEqual(template["containers"][0]["env"][0]["value"], "http://localhost:8000")
        self.assertEqual(template["containers"][1]["env"][0]["value"], "redis://localhost:6379/0")

    def test_rejects_cross_target_state(self) -> None:
        self.state["deploymentEnabled"] = True
        self.state["target"] = "aks"
        with self.assertRaises(ContainerAppsRevisionError):
            validate_desired_state(self.state)

    def test_terraform_and_workflows_preserve_rollout_boundary(self) -> None:
        terraform = "\n".join(path.read_text() for path in (REPO_ROOT / "terraform/container-apps").glob("*.tf"))
        deploy = (REPO_ROOT / ".github/workflows/deploy-container-apps.yml").read_text()
        monitor = (REPO_ROOT / ".github/workflows/monitor-live-demo.yml").read_text()
        for expected in ("azurerm_container_app", 'external_enabled = true', 'target_port      = 8080', 'revision_mode                = "Multiple"', 'revision_suffix = "bootstrap"', "ignore_changes"):
            self.assertIn(expected, terraform)
        self.assertNotIn("latest_revision = true", terraform)
        self.assertIn('default     = 25', terraform)
        self.assertIn('var.monthly_budget_target_usd == 25', terraform)
        for expected in ("environment: container-apps", "candidate-revision.json", "internal/identity", "websocket", "ingress traffic set", "previous_revision", "repair"):
            self.assertIn(expected, deploy.lower())
        self.assertIn("external_monitor.py", monitor)


if __name__ == "__main__":
    unittest.main()
