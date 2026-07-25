from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

UTILS = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "promotion"
sys.path.insert(0, str(UTILS))

from prepare_target_promotion import (  # noqa: E402
    PromotionError,
    TARGETS,
    prepare_promotion,
)


class PrepareTargetPromotionTest(unittest.TestCase):
    def load_fixture(self, name: str) -> dict:
        return json.loads((FIXTURES / name).read_text())

    def prepare_fixture(
        self,
        target: str,
        *,
        manifest: str = "paired-release-manifest.json",
        desired_fixture: str | None = None,
    ) -> dict:
        return prepare_promotion(
            target_name=target,
            release_tag="v1.2.3",
            manifest=self.load_fixture(manifest),
            desired_state=self.load_fixture(
                desired_fixture or f"{target}-desired-state.json"
            ),
        )

    def run_cli(
        self,
        target: str,
        *,
        manifest: str = "paired-release-manifest.json",
        desired_fixture: str | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict, str, set[str]]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_path = root / TARGETS[target]["desired_state_path"]
            target_path.parent.mkdir(parents=True)
            shutil.copy(
                FIXTURES / (desired_fixture or f"{target}-desired-state.json"),
                target_path,
            )
            body_path = root / "pr.md"
            github_output = root / "github-output.txt"
            environment = {**os.environ, "GITHUB_OUTPUT": str(github_output)}
            result = subprocess.run(
                [
                    sys.executable,
                    str(UTILS / "prepare_target_promotion.py"),
                    "--target",
                    target,
                    "--release-tag",
                    "v1.2.3",
                    "--manifest",
                    str(FIXTURES / manifest),
                    "--pr-body-output",
                    str(body_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=root,
                env=environment,
            )
            promoted = json.loads(target_path.read_text())
            body = body_path.read_text() if body_path.exists() else ""
            outputs = (
                set(github_output.read_text().splitlines())
                if github_output.exists()
                else set()
            )
            return result, promoted, body, outputs

    def test_prepares_target_scoped_promotions_through_public_function(self) -> None:
        for target, expected_marker in (
            ("aks", "AKS Deployment Target"),
            ("container-apps", "container-apps Live Demo Environment"),
        ):
            with self.subTest(target=target):
                promotion = self.prepare_fixture(target)
                promoted = promotion["desired_state"]
                self.assertEqual(
                    promoted["webImage"]["digest"], "sha256:" + "b" * 64
                )
                self.assertEqual(
                    promoted["apiImage"]["digest"], "sha256:" + "c" * 64
                )
                self.assertIn(expected_marker, promotion["pr_body"])
                self.assertIn(TARGETS[target]["desired_state_path"], promotion["pr_body"])
                self.assertIn("Artifact provenance: verified", promotion["pr_body"])
                self.assertNotIn("Manifest SHA-256", promotion["pr_body"])
                if target == "container-apps":
                    self.assertEqual(
                        set(promoted),
                        {"deploymentEnabled", "webImage", "apiImage", "redisImage"},
                    )
                    self.assertTrue(promoted["deploymentEnabled"])
                else:
                    self.assertEqual(promoted["ingress"]["host"], "proof.invalid")

    def test_rejects_partial_release_pair(self) -> None:
        with self.assertRaisesRegex(PromotionError, "missing promotion evidence"):
            self.prepare_fixture(
                "aks", manifest="partial-paired-release-manifest.json"
            )

    def test_matching_target_release_is_a_no_op(self) -> None:
        promotion = self.prepare_fixture(
            "aks", desired_fixture="aks-promoted-desired-state.json"
        )
        self.assertEqual(
            promotion["desired_state"], self.load_fixture("aks-promoted-desired-state.json")
        )
        self.assertEqual(promotion["outputs"]["promotion_required"], "false")

    def test_replaces_stale_runtime_images(self) -> None:
        desired_state = self.load_fixture("container-apps-desired-state.json")
        desired_state.update(
            {
                "deploymentEnabled": False,
                "webImage": {"repository": "stale"},
                "apiImage": {"digest": "stale"},
            }
        )
        promotion = prepare_promotion(
            target_name="container-apps",
            release_tag="v1.2.3",
            manifest=self.load_fixture("paired-release-manifest.json"),
            desired_state=desired_state,
        )
        promoted = promotion["desired_state"]
        self.assertTrue(promoted["deploymentEnabled"])
        self.assertEqual(promoted["webImage"]["digest"], "sha256:" + "b" * 64)
        self.assertEqual(promoted["apiImage"]["digest"], "sha256:" + "c" * 64)

    def test_rejects_mismatched_release_evidence(self) -> None:
        with self.assertRaisesRegex(PromotionError, "requested release tag"):
            prepare_promotion(
                target_name="aks",
                release_tag="v1.2.4",
                manifest=self.load_fixture("paired-release-manifest.json"),
                desired_state=self.load_fixture("aks-desired-state.json"),
            )

    def test_rejects_unknown_manifest_schema(self) -> None:
        manifest = self.load_fixture("paired-release-manifest.json")
        manifest["schemaVersion"] = 999

        with self.assertRaisesRegex(PromotionError, "schema is not supported"):
            prepare_promotion(
                target_name="aks",
                release_tag="v1.2.3",
                manifest=manifest,
                desired_state=self.load_fixture("aks-desired-state.json"),
            )

    def test_rejects_evidence_that_cannot_be_used_safely(self) -> None:
        manifest = self.load_fixture("paired-release-manifest.json")
        manifest["images"]["web"]["digest"] = "latest"

        with self.assertRaisesRegex(PromotionError, "digest is invalid"):
            prepare_promotion(
                target_name="aks",
                release_tag="v1.2.3",
                manifest=manifest,
                desired_state=self.load_fixture("aks-desired-state.json"),
            )

    def test_prepare_uses_closed_target_metadata(self) -> None:
        promotion = self.prepare_fixture("aks")
        self.assertEqual(
            promotion["outputs"]["promotion_branch"], "automation/aks-promotion"
        )
        with self.assertRaisesRegex(PromotionError, "target must be one of"):
            prepare_promotion(
                target_name="all",
                release_tag="v1.2.3",
                manifest={},
                desired_state={},
            )

    def test_cli_smoke_covers_parsing_files_body_and_step_outputs(self) -> None:
        result, promoted, body, outputs = self.run_cli("aks")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(promoted["webImage"]["digest"], "sha256:" + "b" * 64)
        self.assertEqual(promoted["apiImage"]["digest"], "sha256:" + "c" * 64)
        self.assertEqual(promoted["ingress"]["host"], "proof.invalid")
        self.assertIn("AKS Deployment Target", body)
        self.assertIn(TARGETS["aks"]["desired_state_path"], body)
        self.assertIn("Artifact provenance: verified", body)
        self.assertEqual(
            outputs,
            {
                "desired_state_path=targets/aks/gitops/halligalli/values/aks.values.json",
                "promotion_branch=automation/aks-promotion",
                "commit_message=chore(aks): promote Halligalli v1.2.3",
                "commit=" + "a" * 40,
                "web_image=ghcr.io/optiplex331/halligalli-bossyang-web@sha256:"
                + "b" * 64,
                "api_image=ghcr.io/optiplex331/halligalli-bossyang-api@sha256:"
                + "c" * 64,
                "promotion_required=true",
            },
        )


if __name__ == "__main__":
    unittest.main()
