"""Tests for structured AKS preflight validation."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validate_aks_preflight import (  # noqa: E402
    AksPreflightError,
    validate_desired_state,
    validate_kubernetes_version,
    validate_quota,
    validate_sku,
    validate_subscription,
    write_backend_config,
)


DIGEST = "sha256:" + "a" * 64


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
            }]}
        )
        validate_quota([
            {"name": {"value": "cores"}, "currentValue": 2, "limit": 20},
            {"name": {"value": "StandardDlsv6Family"}, "currentValue": 0, "limit": 8},
        ])
        validate_kubernetes_version(
            {"values": [{"version": "1.35", "patchVersions": {"1.35.5": {}}}]},
            "1.35.5",
        )
        validate_desired_state({
            "releaseVersion": "0.7.2",
            "webImage": {"repository": "example/web", "digest": DIGEST},
            "apiImage": {"repository": "example/api", "digest": DIGEST},
            "redisImage": {"repository": "redis", "digest": DIGEST},
            "ingress": {"host": "proof.invalid", "tlsSecretName": "proof-tls"},
        })

    def test_rejects_wrong_subscription(self) -> None:
        with self.assertRaisesRegex(AksPreflightError, "does not match"):
            validate_subscription({"id": "other", "state": "Enabled"}, "expected")

    def test_rejects_restricted_sku(self) -> None:
        with self.assertRaisesRegex(AksPreflightError, "restricted"):
            validate_sku({"value": [{
                "name": "Standard_D4ls_v6",
                "locations": ["westeurope"],
                "restrictions": [{"type": "Location"}],
            }]})

    def test_rejects_insufficient_family_quota(self) -> None:
        with self.assertRaisesRegex(AksPreflightError, "fewer than 8"):
            validate_quota([
                {"name": {"value": "cores"}, "currentValue": 0, "limit": 20},
                {"name": {"value": "StandardDlsv6Family"}, "currentValue": 1, "limit": 8},
            ])

    def test_rejects_unavailable_kubernetes_patch(self) -> None:
        with self.assertRaisesRegex(AksPreflightError, "not offered"):
            validate_kubernetes_version({"values": [{"version": "1.35.4"}]}, "1.35.5")

    def test_rejects_unpinned_desired_state_image(self) -> None:
        with self.assertRaisesRegex(AksPreflightError, "digest pinned"):
            validate_desired_state({
                "releaseVersion": "0.7.2",
                "webImage": {"repository": "example/web", "digest": "latest"},
                "apiImage": {"repository": "example/api", "digest": DIGEST},
                "redisImage": {"repository": "redis", "digest": DIGEST},
                "ingress": {"host": "proof.invalid", "tlsSecretName": "proof-tls"},
            })

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
