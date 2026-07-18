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
    validate_desired_state,
    validate_kubernetes_version,
    validate_quota,
    validate_sku,
    validate_subscription,
    write_backend_config,
)


DIGEST = "sha256:" + "a" * 64
TARGET = {
    "region": "westeurope",
    "nodeSku": "Standard_D4ls_v6",
    "nodeCount": 2,
    "vcpusPerNode": 4,
    "quotaFamily": "StandardDlsv6Family",
}


def desired_state() -> dict[str, object]:
    return {
        "releaseVersion": "0.7.2",
        "webImage": {"repository": "example/web", "digest": DIGEST},
        "apiImage": {"repository": "example/api", "digest": DIGEST},
        "redisImage": {"repository": "redis", "digest": DIGEST},
        "redisSecretName": "halligalli-redis-auth",
        "ingress": {"host": "proof.invalid", "tlsSecretName": "proof-tls"},
    }


class ValidateAksPreflightTest(unittest.TestCase):
    def test_accepts_available_approved_target(self) -> None:
        self.assertEqual(
            validate_subscription({"id": "expected", "name": "Demo", "state": "Enabled"}, "expected"),
            {"id": "expected", "name": "Demo"},
        )
        validate_sku(
            {"value": [{
                "name": "Standard_D4ls_v6",
                "locations": ["westeurope"],
                "restrictions": [],
                "family": "StandardDlsv6Family",
                "capabilities": [{"name": "vCPUs", "value": "4"}],
            }]},
            TARGET,
        )
        validate_quota(
            [
                {"name": {"value": "cores"}, "currentValue": 2, "limit": 20},
                {"name": {"value": "StandardDlsv6Family"}, "currentValue": 0, "limit": 8},
            ],
            TARGET,
        )
        validate_kubernetes_version(
            {"values": [{"version": "1.35", "patchVersions": {"1.35.5": {}}}]},
            "1.35.5",
            TARGET,
        )
        validate_desired_state(desired_state())

    def test_loads_target_facts_from_terraform_native_configuration(self) -> None:
        target_path = Path(__file__).resolve().parents[3] / "terraform/aks/target.tf.json"
        self.assertEqual(load_target_facts(target_path), TARGET)

    def test_rejects_target_fact_contract_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "target.tf.json"
            path.write_text(
                '{"locals":{"aks_target":{"region":"westeurope",'
                '"nodeSku":"Standard_D4ls_v6","nodeCount":2,"vcpusPerNode":4,'
                '"quotaFamily":"StandardDlsv6Family","requiredVcpus":8}}}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AksPreflightError, "unsupported requiredVcpus"):
                load_target_facts(path)

    def test_changed_terraform_target_cannot_silently_pass_old_sku_evidence(self) -> None:
        changed_target = {**TARGET, "nodeSku": "Standard_D2ls_v6"}
        with self.assertRaisesRegex(AksPreflightError, "Standard_D2ls_v6"):
            validate_sku(
                {"value": [{
                    "name": "Standard_D4ls_v6",
                    "locations": ["westeurope"],
                    "restrictions": [],
                    "family": "StandardDlsv6Family",
                    "capabilities": [{"name": "vCPUs", "value": "4"}],
                }]},
                changed_target,
            )

    def test_rejects_wrong_subscription(self) -> None:
        with self.assertRaisesRegex(AksPreflightError, "does not match"):
            validate_subscription({"id": "other", "state": "Enabled"}, "expected")

    def test_rejects_restricted_sku(self) -> None:
        with self.assertRaisesRegex(AksPreflightError, "restricted"):
            validate_sku(
                {"value": [{
                    "name": "Standard_D4ls_v6",
                    "locations": ["westeurope"],
                    "restrictions": [{"type": "Location"}],
                    "family": "StandardDlsv6Family",
                    "capabilities": [{"name": "vCPUs", "value": "4"}],
                }]},
                TARGET,
            )

    def test_rejects_node_shape_metadata_that_disagrees_with_azure_sku(self) -> None:
        changed_target = {**TARGET, "vcpusPerNode": 8}
        with self.assertRaisesRegex(AksPreflightError, "target vcpusPerNode 8"):
            validate_sku(
                {"value": [{
                    "name": "Standard_D4ls_v6",
                    "locations": ["westeurope"],
                    "restrictions": [],
                    "family": "StandardDlsv6Family",
                    "capabilities": [{"name": "vCPUs", "value": "4"}],
                }]},
                changed_target,
            )

    def test_rejects_insufficient_family_quota(self) -> None:
        with self.assertRaisesRegex(AksPreflightError, "fewer than 8"):
            validate_quota(
                [
                    {"name": {"value": "cores"}, "currentValue": 0, "limit": 20},
                    {"name": {"value": "StandardDlsv6Family"}, "currentValue": 1, "limit": 8},
                ],
                TARGET,
            )

    def test_rejects_unavailable_kubernetes_patch(self) -> None:
        with self.assertRaisesRegex(AksPreflightError, "not offered"):
            validate_kubernetes_version(
                {"values": [{"version": "1.35.4"}]}, "1.35.5", TARGET
            )

    def test_rejects_unpinned_desired_state_image(self) -> None:
        with self.assertRaisesRegex(AksPreflightError, "digest pinned"):
            state = desired_state()
            state["webImage"] = {"repository": "example/web", "digest": "latest"}
            validate_desired_state(state)

    def test_rejects_missing_redis_secret_name(self) -> None:
        state = desired_state()
        del state["redisSecretName"]
        with self.assertRaisesRegex(AksPreflightError, "missing redisSecretName"):
            validate_desired_state(state)

    def test_rejects_invalid_kubernetes_ingress_name(self) -> None:
        state = desired_state()
        state["ingress"] = {"host": "proof.invalid", "tlsSecretName": "Invalid_Name"}
        with self.assertRaisesRegex(AksPreflightError, "TLS Secret name"):
            validate_desired_state(state)

    def test_rejects_invalid_ingress_host_label(self) -> None:
        state = desired_state()
        state["ingress"] = {"host": f"{'a' * 64}.invalid", "tlsSecretName": "proof-tls"}
        with self.assertRaisesRegex(AksPreflightError, "ingress host"):
            validate_desired_state(state)

    def test_rejects_extra_desired_state_fields_at_every_level(self) -> None:
        cases = []
        top_level = desired_state()
        top_level["replicas"] = 2
        cases.append(top_level)
        image = desired_state()
        image["webImage"] = {"repository": "example/web", "digest": DIGEST, "tag": "latest"}
        cases.append(image)
        ingress = desired_state()
        ingress["ingress"] = {
            "host": "proof.invalid",
            "tlsSecretName": "proof-tls",
            "className": "nginx",
        }
        cases.append(ingress)

        for state in cases:
            with self.subTest(state=state), self.assertRaisesRegex(
                AksPreflightError, "unsupported"
            ):
                validate_desired_state(state)

    def test_writes_backend_config_for_the_selected_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backend.hcl"
            write_backend_config(path, "example-org", "aks")
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                'organization = "example-org"\n\nworkspaces {\n  name = "aks"\n}\n',
            )

    def test_rejects_backend_config_injection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AksPreflightError, "unsupported characters"):
                write_backend_config(Path(directory) / "backend.hcl", 'example"', "aks")


if __name__ == "__main__":
    unittest.main()
