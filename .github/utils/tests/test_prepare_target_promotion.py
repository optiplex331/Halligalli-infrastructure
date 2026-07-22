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
    prepare_promotion,
    resolve_promotion_request,
)


class PrepareTargetPromotionTest(unittest.TestCase):
    def run_prepare(self, target: str, *, manifest: str = "paired-release-manifest.json", desired_fixture: str | None = None) -> tuple[subprocess.CompletedProcess[str], dict, str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_path = root / resolve_promotion_request(target, "v1.2.3")["desired_state_path"]
            target_path.parent.mkdir(parents=True)
            shutil.copy(FIXTURES / (desired_fixture or f"{target}-desired-state.json"), target_path)
            output_path = root / "promoted.json"
            body_path = root / "pr.md"
            github_output = root / "github-output.txt"
            environment = {**os.environ, "GITHUB_OUTPUT": str(github_output)}
            result = subprocess.run(
                [
                    sys.executable,
                    str(UTILS / "prepare_target_promotion.py"),
                    "prepare",
                    "--target",
                    target,
                    "--release-tag",
                    "v1.2.3",
                    "--manifest",
                    str(FIXTURES / manifest),
                    "--repo-root",
                    str(root),
                    "--output",
                    str(output_path),
                    "--pr-body-output",
                    str(body_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            promoted = json.loads(output_path.read_text()) if output_path.exists() else {}
            body = body_path.read_text() if body_path.exists() else ""
            return result, promoted, body

    def test_shared_interface_prepares_both_target_scoped_promotions(self) -> None:
        for target, expected_marker in (
            ("aks", "AKS Deployment Target"),
            ("container-apps", "container-apps Live Demo Environment"),
        ):
            with self.subTest(target=target):
                result, promoted, body = self.run_prepare(target)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(promoted["releaseVersion"], "1.2.3")
                self.assertEqual(promoted["webImage"]["digest"], "sha256:" + "b" * 64)
                self.assertEqual(promoted["apiImage"]["digest"], "sha256:" + "c" * 64)
                self.assertIn(expected_marker, body)
                self.assertIn(
                    resolve_promotion_request(target, "v1.2.3")["desired_state_path"],
                    body,
                )
                self.assertIn("Artifact provenance: verified", body)
                self.assertNotIn("Manifest SHA-256", body)
                if target == "container-apps":
                    self.assertEqual(promoted["target"], "container-apps")
                    self.assertEqual(promoted["releaseCommit"], "a" * 40)
                    self.assertTrue(promoted["deploymentEnabled"])
                else:
                    self.assertNotIn("target", promoted)
                    self.assertEqual(promoted["ingress"]["host"], "proof.invalid")

    def test_rejects_cross_target_desired_state(self) -> None:
        result, promoted, _ = self.run_prepare("container-apps", desired_fixture="aks-desired-state.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(promoted)
        self.assertIn("container-apps desired state", result.stderr)

    def test_rejects_partial_release_pair(self) -> None:
        result, promoted, _ = self.run_prepare("aks", manifest="partial-paired-release-manifest.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(promoted)
        self.assertIn("complete Web and API images", result.stderr)

    def test_matching_target_release_is_a_no_op(self) -> None:
        result, promoted, _ = self.run_prepare("aks", desired_fixture="aks-promoted-desired-state.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(promoted["releaseVersion"], "1.2.3")
        self.assertIn('"promotion_required": "false"', result.stdout)

    def test_replaces_stale_release_fields_as_one_pair(self) -> None:
        desired_state = json.loads((FIXTURES / "container-apps-desired-state.json").read_text())
        desired_state.update(
            {
                "releaseVersion": None,
                "releaseCommit": "not-a-commit",
                "deploymentEnabled": False,
                "webImage": {"repository": "stale"},
                "apiImage": {"digest": "stale"},
            }
        )
        promotion = prepare_promotion(
            target_name="container-apps",
            release_tag="v1.2.3",
            manifest=json.loads((FIXTURES / "paired-release-manifest.json").read_text()),
            desired_state=desired_state,
        )
        self.assertEqual(promotion["desired_state"]["releaseVersion"], "1.2.3")
        self.assertEqual(promotion["desired_state"]["releaseCommit"], "a" * 40)
        self.assertTrue(promotion["desired_state"]["deploymentEnabled"])
        self.assertEqual(promotion["desired_state"]["webImage"]["digest"], "sha256:" + "b" * 64)
        self.assertEqual(promotion["desired_state"]["apiImage"]["digest"], "sha256:" + "c" * 64)

    def test_rejects_mismatched_release_evidence(self) -> None:
        manifest = json.loads((FIXTURES / "paired-release-manifest.json").read_text())
        desired_state = json.loads((FIXTURES / "aks-desired-state.json").read_text())
        with self.assertRaisesRegex(PromotionError, "requested release tag"):
            prepare_promotion(
                target_name="aks",
                release_tag="v1.2.4",
                manifest=manifest,
                desired_state=desired_state,
            )

    def test_rejects_mutable_or_inconsistent_release_evidence(self) -> None:
        desired_state = json.loads((FIXTURES / "aks-desired-state.json").read_text())
        cases = []
        mixed = json.loads((FIXTURES / "paired-release-manifest.json").read_text())
        mixed["images"]["api"]["tag"] = "1.2.4"
        cases.append(mixed)
        mutable = json.loads((FIXTURES / "paired-release-manifest.json").read_text())
        mutable["images"]["web"]["digest"] = "latest"
        cases.append(mutable)
        inconsistent = json.loads((FIXTURES / "paired-release-manifest.json").read_text())
        inconsistent["runtimeIdentity"]["commit"] = "d" * 40
        cases.append(inconsistent)
        for manifest in cases:
            with self.subTest(manifest=manifest), self.assertRaises(PromotionError):
                prepare_promotion(
                    target_name="aks",
                    release_tag="v1.2.3",
                    manifest=manifest,
                    desired_state=desired_state,
                )

    def test_resolve_uses_closed_target_metadata(self) -> None:
        self.assertEqual(
            resolve_promotion_request("aks", "v1.2.3")["promotion_branch"],
            "automation/aks-promotion",
        )
        self.assertEqual(
            resolve_promotion_request("container-apps", "v1.2.3")["promotion_branch"],
            "automation/container-apps-promotion",
        )
        with self.assertRaisesRegex(PromotionError, "target must be one of"):
            resolve_promotion_request("all", "v1.2.3")

    def test_resolve_writes_step_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment_path = root / "github-env.txt"
            output_path = root / "github-output.txt"
            result = subprocess.run(
                [
                    sys.executable,
                    str(UTILS / "prepare_target_promotion.py"),
                    "resolve",
                    "--target",
                    "aks",
                    "--release-tag",
                    "v1.2.3",
                ],
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "GITHUB_ENV": str(environment_path),
                    "GITHUB_OUTPUT": str(output_path),
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(environment_path.exists())
            self.assertEqual(
                set(output_path.read_text().splitlines()),
                {
                    "target=aks",
                    "release_tag=v1.2.3",
                    "desired_state_path=targets/aks/gitops/values/halligalli.values.json",
                    "promotion_branch=automation/aks-promotion",
                    "asset_url=https://github.com/optiplex331/Halligalli-BossYang/releases/download/v1.2.3/paired-release-manifest.json",
                    "commit_message=chore(aks): promote Halligalli v1.2.3",
                },
            )


if __name__ == "__main__":
    unittest.main()
