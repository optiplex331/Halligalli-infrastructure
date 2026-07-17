"""Tests for AKS Deployment Target Terraform configuration generation."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import write_aks_terraform_config  # noqa: E402


class WriteAksTerraformConfigTest(unittest.TestCase):
    def test_generates_backend_and_tfvars_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            backend_path = Path(directory) / "backend.hcl"
            tfvars_path = Path(directory) / "terraform.auto.tfvars.json"
            env = {
                "HALLIGALLI_AKS_TERRAFORM_OPERATION": "plan",
                "TERRAFORM_BACKEND_CONFIG_PATH": str(backend_path),
                "TERRAFORM_TFVARS_JSON_PATH": str(tfvars_path),
                "HCP_TERRAFORM_ORGANIZATION": "example-org",
                "HCP_TERRAFORM_WORKSPACE": "aks",
                "HALLIGALLI_AKS_DOMAIN_NAME": "halligalli.games",
            }

            with patch.dict(os.environ, env, clear=True):
                write_aks_terraform_config.main()

            self.assertEqual(
                backend_path.read_text(encoding="utf-8"),
                'organization = "example-org"\n\nworkspaces {\n  name = "aks"\n}\n',
            )
            tfvars = json.loads(tfvars_path.read_text(encoding="utf-8"))

        self.assertEqual(tfvars["domain_name"], "halligalli.games")
        self.assertEqual(
            set(tfvars),
            {"domain_name"},
        )

    def test_rejects_removed_managed_telemetry_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = {
                "HALLIGALLI_AKS_TERRAFORM_OPERATION": "plan",
                "TERRAFORM_BACKEND_CONFIG_PATH": str(Path(directory) / "backend.hcl"),
                "TERRAFORM_TFVARS_JSON_PATH": str(Path(directory) / "terraform.auto.tfvars.json"),
                "HCP_TERRAFORM_ORGANIZATION": "example-org",
                "HCP_TERRAFORM_WORKSPACE": "aks",
                "HALLIGALLI_AKS_DOMAIN_NAME": "halligalli.games",
                "HALLIGALLI_AKS_ENABLE_CONTAINER_INSIGHTS": "true",
                "HALLIGALLI_AKS_LOG_ANALYTICS_RETENTION_DAYS": "30",
            }

            with patch.dict(os.environ, env, clear=True):
                with self.assertRaisesRegex(SystemExit, "not supported"):
                    write_aks_terraform_config.main()

    def test_rejects_unknown_operation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = {
                "HALLIGALLI_AKS_TERRAFORM_OPERATION": "scale-down",
                "TERRAFORM_BACKEND_CONFIG_PATH": str(Path(directory) / "backend.hcl"),
                "TERRAFORM_TFVARS_JSON_PATH": str(Path(directory) / "terraform.auto.tfvars.json"),
                "HCP_TERRAFORM_ORGANIZATION": "example-org",
                "HCP_TERRAFORM_WORKSPACE": "aks",
                "HALLIGALLI_AKS_DOMAIN_NAME": "halligalli.games",
            }

            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(SystemExit):
                    write_aks_terraform_config.main()


if __name__ == "__main__":
    unittest.main()
