"""Tests for structured AKS preflight validation."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validate_aks_preflight import (  # noqa: E402
    AksPreflightError,
    load_target_facts,
    validate_kubernetes_version,
    validate_quota,
    validate_sku,
    validate_subscription,
    write_backend_config,
)


TARGET = {
    "region": "northeurope",
    "nodeSku": "Standard_D4ls_v6",
    "nodeCount": 2,
    "kubernetesVersion": "1.36.1",
}

SKU = {
    "value": [
        {
            "name": "Standard_D4ls_v6",
            "locations": ["northeurope"],
            "restrictions": [],
            "family": "StandardDlsv6Family",
            "capabilities": [{"name": "vCPUs", "value": "4"}],
        }
    ]
}

QUOTA_FAMILY = "StandardDlsv6Family"
VCPUS_PER_NODE = 4
CAPACITY = (QUOTA_FAMILY, VCPUS_PER_NODE)


class ValidateAksPreflightTest(unittest.TestCase):
    def assert_rejections(self, cases) -> None:
        for name, operation, pattern in cases:
            with self.subTest(case=name), self.assertRaisesRegex(AksPreflightError, pattern):
                operation()

    def test_accepts_available_approved_target(self) -> None:
        self.assertEqual(
            validate_subscription({"id": "expected", "name": "Demo", "state": "Enabled"}, "expected"),
            {"id": "expected", "name": "Demo"},
        )
        self.assertEqual(validate_sku(SKU, TARGET), CAPACITY)
        validate_quota(
            [
                {"name": {"value": "cores"}, "currentValue": 2, "limit": 20},
                {"name": {"value": "StandardDlsv6Family"}, "currentValue": 0, "limit": 8},
            ],
            TARGET,
            quota_family=QUOTA_FAMILY,
            vcpus_per_node=VCPUS_PER_NODE,
        )
        validate_kubernetes_version(
            {"values": [{"version": "1.36", "patchVersions": {"1.36.1": {}}}]},
            TARGET["kubernetesVersion"],
            TARGET,
        )

    def test_loads_target_facts_from_checked_in_json(self) -> None:
        target_path = Path(__file__).resolve().parents[3] / "targets/aks/terraform/target.json"
        self.assertEqual(load_target_facts(target_path), TARGET)

    def test_rejects_invalid_target_facts(self) -> None:
        cases = (
            (
                "unsupported derived fact",
                '{"region":"northeurope","nodeSku":"Standard_D4ls_v6",'
                '"nodeCount":2,"kubernetesVersion":"1.36.1","requiredVcpus":8}',
                "unsupported requiredVcpus",
            ),
            (
                "incomplete Kubernetes version",
                '{"region":"northeurope","nodeSku":"Standard_D4ls_v6",'
                '"nodeCount":2,"kubernetesVersion":"1.36"}',
                "full version",
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, (name, raw_target, pattern) in enumerate(cases):
                with self.subTest(case=name):
                    path = Path(directory) / f"target-{index}.json"
                    path.write_text(raw_target, encoding="utf-8")
                    with self.assertRaisesRegex(AksPreflightError, pattern):
                        load_target_facts(path)

    def test_rejects_invalid_subscriptions(self) -> None:
        self.assert_rejections(
            (
                ("unexpected subscription", lambda: validate_subscription({"id": "other", "state": "Enabled"}, "expected"), "does not match"),
                ("disabled subscription", lambda: validate_subscription({"id": "expected", "state": "Disabled"}, "expected"), "not enabled"),
            )
        )

    def test_rejects_invalid_skus(self) -> None:
        changed_target = {**TARGET, "nodeSku": "Standard_D2ls_v6"}
        restricted_sku = {"value": [{**SKU["value"][0], "restrictions": [{"type": "Location"}]}]}
        self.assert_rejections(
            (
                ("target SKU has no matching evidence", lambda: validate_sku(SKU, changed_target), "Standard_D2ls_v6"),
                ("SKU is subscription-restricted", lambda: validate_sku(restricted_sku, TARGET), "restricted"),
            )
        )

    def test_rejects_invalid_quotas(self) -> None:
        self.assert_rejections(
            (
                (
                    "family quota is insufficient",
                    lambda: validate_quota(
                        [
                            {"name": {"value": "cores"}, "currentValue": 0, "limit": 20},
                            {"name": {"value": QUOTA_FAMILY}, "currentValue": 1, "limit": 8},
                        ], TARGET, quota_family=QUOTA_FAMILY, vcpus_per_node=VCPUS_PER_NODE
                    ),
                    "fewer than 8",
                ),
                (
                    "required cores quota is absent",
                    lambda: validate_quota(
                        [{"name": {"value": QUOTA_FAMILY}, "currentValue": 0, "limit": 8}],
                        TARGET, quota_family=QUOTA_FAMILY, vcpus_per_node=VCPUS_PER_NODE
                    ),
                    "Required Azure quota cores was not returned",
                ),
            )
        )

    def test_rejects_invalid_kubernetes_version_responses(self) -> None:
        self.assert_rejections(
            (
                (
                    "target patch is unavailable",
                    lambda: validate_kubernetes_version(
                        {"values": [{"version": "1.36", "patchVersions": {}}]}, TARGET["kubernetesVersion"], TARGET
                    ),
                    "not offered",
                ),
                (
                    "patch in unrelated response field is ignored",
                    lambda: validate_kubernetes_version(
                        {"note": "1.36.1", "values": [{"version": "1.36", "patchVersions": {}}]}, TARGET["kubernetesVersion"], TARGET
                    ),
                    "not offered",
                ),
                (
                    "version response has no values list",
                    lambda: validate_kubernetes_version({}, TARGET["kubernetesVersion"], TARGET),
                    "value list",
                ),
                (
                    "version entry has malformed patch versions",
                    lambda: validate_kubernetes_version(
                        {"values": [{"version": "1.35", "patchVersions": {"1.35.5": {}}}, {"version": "1.36", "patchVersions": []}]}, TARGET["kubernetesVersion"], TARGET
                    ),
                    "entry is malformed",
                ),
            )
        )

    def test_writes_backend_config_for_the_selected_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backend.hcl"
            write_backend_config(path, "example-org", "aks")
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                'organization = "example-org"\n\nworkspaces {\n  name = "aks"\n}\n',
            )

    def test_rejects_unsafe_backend_config_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assert_rejections(
                (
                    (
                        "organization contains quote",
                        lambda: write_backend_config(Path(directory) / "organization.hcl", 'example"', "aks"),
                        "unsupported characters",
                    ),
                    (
                        "workspace contains path separator",
                        lambda: write_backend_config(Path(directory) / "workspace.hcl", "example-org", "aks/prod"),
                        "unsupported characters",
                    ),
                )
            )


if __name__ == "__main__":
    unittest.main()
