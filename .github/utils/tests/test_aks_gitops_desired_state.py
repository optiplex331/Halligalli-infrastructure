"""Rendered AKS contracts that native schema validation cannot express."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
GITOPS_ROOT = REPO_ROOT / "gitops" / "aks"
VALUES_PATH = GITOPS_ROOT / "values" / "halligalli.values.json"
CHART_PATH = GITOPS_ROOT / "chart" / "halligalli"


def render_chart() -> str:
    return subprocess.run(
        ["helm", "template", "halligalli", str(CHART_PATH), "--values", str(VALUES_PATH)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


class AksRenderedBoundaryTest(unittest.TestCase):
    def test_rendered_runtime_enforces_security_and_network_boundaries(self) -> None:
        rendered = render_chart()

        self.assertEqual(rendered.count("kind: NetworkPolicy\n"), 4)
        self.assertIn("name: halligalli-default-deny", rendered)
        self.assertIn("type: RuntimeDefault", rendered)
        self.assertIn("allowPrivilegeEscalation: false", rendered)
        self.assertIn('drop: ["ALL"]', rendered)
        self.assertIn("readOnlyRootFilesystem: true", rendered)
        self.assertNotIn("HALLIGALLI_RELEASE_VERSION", rendered)
        self.assertNotIn("HALLIGALLI_RELEASE_COMMIT", rendered)
        self.assertIn("k8s-app: kube-dns", rendered)

    def test_redis_secret_operation_is_approval_gated_and_does_not_render_a_credential(self) -> None:
        rendered = render_chart()
        blocked = subprocess.run(
            ["sh", str(GITOPS_ROOT / "scripts" / "apply-redis-auth-secret.sh")],
            capture_output=True,
            text=True,
        )

        self.assertNotIn("password:", rendered)
        self.assertNotIn("stringData:", rendered)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("HALLIGALLI_OPERATION_APPROVED=1", blocked.stderr)


if __name__ == "__main__":
    unittest.main()
