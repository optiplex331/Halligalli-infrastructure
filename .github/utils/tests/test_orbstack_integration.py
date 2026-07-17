"""Static contract for the disposable one-node OrbStack helper."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER_PATH = REPO_ROOT / "gitops" / "aks" / "scripts" / "orbstack-integration.sh"


class OrbStackIntegrationHelperTest(unittest.TestCase):
    def test_helper_keeps_orbstack_local_and_aks_values_closed(self) -> None:
        helper = HELPER_PATH.read_text(encoding="utf-8")

        self.assertIn("HALLIGALLI_ORBSTACK_APPROVED=1", helper)
        self.assertIn("orbstack", helper)
        self.assertIn("halligalli-orbstack", helper)
        self.assertIn("helm template", helper)
        self.assertIn("halligalli-observability", helper)
        self.assertIn("networkpolicy", helper.lower())
        self.assertIn("one-node", helper)
        self.assertIn("does not prove", helper)
        self.assertNotIn("az ", helper)
        self.assertNotIn("terraform apply", helper)


if __name__ == "__main__":
    unittest.main()
