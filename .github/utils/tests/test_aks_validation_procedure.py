"""Static contract for the approval-gated AKS Validation Run procedure."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER = REPO_ROOT / "gitops/aks/scripts/aks-validation-preflight.sh"
EVIDENCE = REPO_ROOT / "evidence/aks-validation-summary.json"
EVIDENCE_TEMPLATE = REPO_ROOT / "evidence/aks-portfolio-proof-record.template.json"
RUNTIME_VALUES = REPO_ROOT / "gitops/aks/values/halligalli.values.json"
OBSERVABILITY_VALUES = REPO_ROOT / "gitops/aks/values/halligalli-observability.values.json"
PROCEDURE = REPO_ROOT / "docs/operations/aks-validation.md"


class AksValidationProcedureTest(unittest.TestCase):
    def test_preflight_is_approval_gated_and_read_only(self) -> None:
        helper = HELPER.read_text(encoding="utf-8")

        self.assertIn('HALLIGALLI_OPERATION_APPROVED:-}" != "1"', helper)
        self.assertNotIn("terraform apply", helper)
        self.assertNotIn("terraform destroy", helper)
        self.assertNotIn("kubectl ", helper)
        self.assertNotIn("USD 4", helper)
        self.assertIn("HALLIGALLI_AKS_MINIMUM_CREDIT_USD", helper)

    def test_sanitized_v072_summary_matches_the_maintained_desired_state(self) -> None:
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        runtime_values = json.loads(RUNTIME_VALUES.read_text(encoding="utf-8"))
        observability_values = json.loads(OBSERVABILITY_VALUES.read_text(encoding="utf-8"))
        identity = evidence["release"]

        self.assertEqual(evidence["schemaVersion"], 1)
        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(identity["releaseTag"], "v0.7.2")
        self.assertEqual(evidence["runtime"]["nodeCount"], 2)
        self.assertEqual(runtime_values["releaseVersion"], "0.7.2")
        self.assertEqual(runtime_values["webImage"]["digest"], identity["webDigest"])
        self.assertEqual(runtime_values["apiImage"]["digest"], identity["apiDigest"])
        self.assertEqual(runtime_values["redisImage"]["digest"], identity["redisDigest"])
        for component in ("prometheus", "grafana", "collector", "tempo"):
            self.assertEqual(
                observability_values[f"{component}Image"]["digest"],
                evidence["dependencies"][f"{component}Digest"],
            )

        self.assertEqual(evidence["checks"]["apiDisruption"], "passed")
        self.assertEqual(evidence["checks"]["sameOriginJourneys"], "passed")
        self.assertEqual(evidence["checks"]["nonRedisNodeDrain"], "passed")
        self.assertEqual(evidence["checks"]["gitopsDriftCorrection"], "passed")
        self.assertEqual(evidence["checks"]["pairedRollback"], "passed")
        self.assertEqual(evidence["checks"]["destroyAndInventory"], "passed")

    def test_new_validation_records_use_current_journey_contract(self) -> None:
        template = json.loads(EVIDENCE_TEMPLATE.read_text(encoding="utf-8"))
        procedure = PROCEDURE.read_text(encoding="utf-8")

        self.assertEqual(template["schemaVersion"], 2)
        self.assertIn("fourSeatTwoHumanJourney", template["checks"])
        self.assertIn("eightSeatTwoHumanJourney", template["checks"])
        self.assertNotIn("twoSeatJourney", template["checks"])
        self.assertNotIn("sixSeatJourney", template["checks"])
        self.assertIn("four-seat/two-human", procedure)
        self.assertIn("eight-seat/two-human", procedure)
        self.assertIn("public summary deliberately omits", procedure)


if __name__ == "__main__":
    unittest.main()
