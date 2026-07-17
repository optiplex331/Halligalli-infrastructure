import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_release_promotion import inspect_runtime_dependencies, resolve_promotion_request  # noqa: E402
from validate_paired_release_manifest import (  # noqa: E402
    PairedReleaseManifestError,
    build_promoted_values,
    validate_file_to_output,
    validate_paired_release_manifest,
    validate_release_evidence,
)


def manifest() -> dict:
    return {
        "schemaVersion": 2, "releaseTag": "v1.2.3", "commit": "a" * 40,
        "images": {
            "web": {"repository": "ghcr.io/optiplex331/halligalli-bossyang-web", "tag": "1.2.3", "digest": "sha256:" + "b" * 64},
            "api": {"repository": "ghcr.io/optiplex331/halligalli-bossyang-api", "tag": "1.2.3", "digest": "sha256:" + "c" * 64},
        }, "runtimeIdentity": {"version": "1.2.3", "commit": "a" * 40},
    }


class PairedReleaseManifestTest(unittest.TestCase):
    def test_resolves_independent_target_promotion_branches(self) -> None:
        self.assertEqual(resolve_promotion_request("v1.2.3")["promotion_branch"], "automation/release-promotion")
        self.assertEqual(resolve_promotion_request("v1.2.3", "automation/container-apps-promotion")["promotion_branch"], "automation/container-apps-promotion")

    def test_accepts_complete_paired_manifest(self) -> None:
        validated = validate_release_evidence(manifest(), expected_tag="v1.2.3")
        self.assertEqual(validated["web_repository"], "ghcr.io/optiplex331/halligalli-bossyang-web")
        self.assertEqual(validated["api_digest"], "sha256:" + "c" * 64)

    def test_writes_validated_candidate_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, output_path = Path(directory) / "paired-release-manifest.json", Path(directory) / "candidate.json"
            manifest_path.write_text(json.dumps(manifest()))
            validated = validate_file_to_output(manifest_path, expected_tag="v1.2.3", output_path=output_path)
            self.assertEqual(json.loads(output_path.read_text()), validated)

    def test_rejects_malformed_or_partial_manifest(self) -> None:
        partial = manifest(); del partial["images"]["api"]
        with self.assertRaisesRegex(PairedReleaseManifestError, "complete Web and API"):
            validate_paired_release_manifest(partial)
        with self.assertRaisesRegex(PairedReleaseManifestError, "requested release tag"):
            validate_release_evidence(manifest(), expected_tag="v1.2.4")

    def test_rejects_mixed_mutable_or_inconsistent_release_evidence(self) -> None:
        cases = []
        mixed = manifest(); mixed["images"]["api"]["tag"] = "1.2.4"; cases.append(mixed)
        mutable = manifest(); mutable["images"]["web"]["digest"] = "latest"; cases.append(mutable)
        inconsistent = manifest(); inconsistent["runtimeIdentity"]["commit"] = "d" * 40; cases.append(inconsistent)
        for candidate in cases:
            with self.subTest(candidate=candidate), self.assertRaises(PairedReleaseManifestError):
                validate_paired_release_manifest(candidate)

    def test_promotes_only_paired_images_version_and_commit(self) -> None:
        values = {"webImage": {"repository": "old-web", "digest": "sha256:" + "0" * 64}, "apiImage": {"repository": "old-api", "digest": "sha256:" + "1" * 64}, "releaseVersion": "old", "releaseCommit": "0" * 40, "redisImage": {"repository": "redis"}}
        original = copy.deepcopy(values)
        promoted = build_promoted_values(values, validate_paired_release_manifest(manifest()))
        self.assertEqual(promoted["releaseVersion"], "1.2.3")
        self.assertEqual(promoted["releaseCommit"], "a" * 40)
        self.assertEqual(promoted["redisImage"], original["redisImage"])
        self.assertEqual(values, original)

    def test_container_apps_promotion_enables_deployment(self) -> None:
        values = {"schemaVersion": 1, "target": "container-apps", "deploymentEnabled": False, "webImage": {}, "apiImage": {}, "releaseVersion": "0.7.2", "releaseCommit": "0" * 40}
        promoted = build_promoted_values(values, validate_paired_release_manifest(manifest()))
        self.assertTrue(promoted["deploymentEnabled"])

    def test_runtime_dependency_inspection_requires_digest_pinned_redis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "values.json"
            path.write_text(json.dumps({"redisImage": {"repository": "redis", "digest": "latest"}}))
            with self.assertRaisesRegex(PairedReleaseManifestError, "digest-pinned redisImage"):
                inspect_runtime_dependencies(path)


if __name__ == "__main__": unittest.main()
