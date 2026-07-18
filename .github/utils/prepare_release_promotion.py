#!/usr/bin/env python3
"""Prepare one target-scoped promotion from formal Paired Release evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from validate_paired_release_manifest import (
    COMMIT_RE,
    PRODUCT_IMAGES,
    TAG_RE,
    PairedReleaseManifestError,
    validate_release_evidence,
)

PRODUCT_REPOSITORY = "optiplex331/Halligalli-BossYang"


@dataclass(frozen=True)
class PromotionTarget:
    desired_state_path: Path
    promotion_branch: str
    commit_scope: str
    display_name: str


TARGETS = {
    "aks": PromotionTarget(
        desired_state_path=Path("gitops/aks/values/halligalli.values.json"),
        promotion_branch="automation/release-promotion",
        commit_scope="gitops",
        display_name="AKS Deployment Target",
    ),
    "container-apps": PromotionTarget(
        desired_state_path=Path("deployment/container-apps/desired-state.json"),
        promotion_branch="automation/container-apps-promotion",
        commit_scope="container-apps",
        display_name="container-apps Live Demo Environment",
    ),
}


def append_command_file(values: dict[str, str], *, environment_name: str, uppercase_names: bool = False) -> None:
    command_file_path = os.environ.get(environment_name, "")
    if not command_file_path:
        return
    with Path(command_file_path).open("a", encoding="utf-8") as command_file:
        for name, value in values.items():
            command_file.write(f"{name.upper() if uppercase_names else name}={value}\n")


def write_outputs(values: dict[str, str]) -> None:
    append_command_file(values, environment_name="GITHUB_OUTPUT")
    print(json.dumps(values, sort_keys=True))


def write_environment(values: dict[str, str]) -> None:
    append_command_file(values, environment_name="GITHUB_ENV", uppercase_names=True)


def resolve_promotion_request(target_name: str, release_tag: str) -> dict[str, str]:
    target = TARGETS.get(target_name)
    if target is None:
        raise PairedReleaseManifestError(f"target must be one of: {', '.join(TARGETS)}")
    if not TAG_RE.fullmatch(release_tag):
        raise PairedReleaseManifestError("release_tag must match vX.Y.Z")
    return {
        "target": target_name,
        "release_tag": release_tag,
        "desired_state_path": target.desired_state_path.as_posix(),
        "promotion_branch": target.promotion_branch,
        "asset_url": f"https://github.com/{PRODUCT_REPOSITORY}/releases/download/{release_tag}/paired-release-manifest.json",
        "commit_message": f"chore({target.commit_scope}): promote Halligalli {release_tag}",
    }


def _require_image(desired_state: dict[str, Any], key: str) -> dict[str, Any]:
    image = desired_state.get(key)
    if not isinstance(image, dict) or set(image) != {"repository", "digest"}:
        raise PairedReleaseManifestError(f"desired state requires a closed {key} selection")
    if not all(isinstance(image[field], str) and image[field] for field in ("repository", "digest")):
        raise PairedReleaseManifestError(f"desired state requires a complete {key} selection")
    return image


def validate_target_desired_state(target_name: str, desired_state: Any) -> dict[str, Any]:
    if target_name not in TARGETS:
        raise PairedReleaseManifestError(f"target must be one of: {', '.join(TARGETS)}")
    if not isinstance(desired_state, dict):
        raise PairedReleaseManifestError("desired state must be a JSON object")
    if not isinstance(desired_state.get("releaseVersion"), str):
        raise PairedReleaseManifestError("desired state requires releaseVersion")
    _require_image(desired_state, "webImage")
    _require_image(desired_state, "apiImage")
    if target_name == "container-apps":
        if desired_state.get("target") != "container-apps":
            raise PairedReleaseManifestError("container-apps promotion requires container-apps desired state")
        if desired_state.get("schemaVersion") != 1:
            raise PairedReleaseManifestError("container-apps desired state requires schemaVersion 1")
        if not isinstance(desired_state.get("deploymentEnabled"), bool):
            raise PairedReleaseManifestError("container-apps desired state requires deploymentEnabled")
        release_commit = desired_state.get("releaseCommit")
        if not isinstance(release_commit, str) or not COMMIT_RE.fullmatch(release_commit):
            raise PairedReleaseManifestError("container-apps desired state requires releaseCommit")
    elif "target" in desired_state:
        raise PairedReleaseManifestError("AKS promotion rejects desired state for another target")
    return desired_state


def build_target_promotion(target_name: str, desired_state: dict[str, Any], candidate: dict[str, str]) -> dict[str, Any]:
    promoted = json.loads(json.dumps(validate_target_desired_state(target_name, desired_state)))
    for role, key in (("web", "webImage"), ("api", "apiImage")):
        promoted[key] = {
            "repository": candidate[f"{role}_repository"],
            "digest": candidate[f"{role}_digest"],
        }
    promoted["releaseVersion"] = candidate["version"]
    if target_name == "container-apps":
        promoted["releaseCommit"] = candidate["commit"]
        promoted["deploymentEnabled"] = True
    validate_target_promotion(target_name, promoted, candidate)
    return promoted


def validate_target_promotion(target_name: str, promoted: dict[str, Any], candidate: dict[str, str]) -> None:
    validate_target_desired_state(target_name, promoted)
    if promoted["releaseVersion"] != candidate["version"]:
        raise PairedReleaseManifestError("promotion must select the formal Release Tag")
    if target_name == "container-apps" and promoted["releaseCommit"] != candidate["commit"]:
        raise PairedReleaseManifestError("promotion must select the exact Product commit")
    for role, key in (("web", "webImage"), ("api", "apiImage")):
        expected = {
            "repository": PRODUCT_IMAGES[role],
            "digest": candidate[f"{role}_digest"],
        }
        if promoted[key] != expected:
            raise PairedReleaseManifestError("promotion requires the complete Web/API digest pair")


def render_promotion_pr_body(
    *, target_name: str, release_tag: str, candidate: dict[str, str], asset_url: str, manifest_sha256: str
) -> str:
    target = TARGETS[target_name]
    return f"""## {target.display_name} promotion

- Release Tag: `{release_tag}`
- Product commit: `{candidate['commit']}`
- Web image: `{candidate['web_repository']}@{candidate['web_digest']}`
- API image: `{candidate['api_repository']}@{candidate['api_digest']}`
- Paired Release Manifest: {asset_url}
- Manifest SHA-256: `{manifest_sha256}`
- Artifact provenance: both digests matched the Product repository, signer workflow, source tag, and source commit

This Draft PR changes only `{target.desired_state_path}` for the {target.display_name}. It neither modifies the other Deployment Target nor deploys infrastructure.
"""


def prepare_promotion(
    *, target_name: str, release_tag: str, manifest_path: Path, repo_root: Path, output_path: Path, pr_body_path: Path
) -> dict[str, str]:
    resolved = resolve_promotion_request(target_name, release_tag)
    target = TARGETS[target_name]
    manifest_bytes = manifest_path.read_bytes()
    candidate = validate_release_evidence(json.loads(manifest_bytes), expected_tag=release_tag)
    desired_state_path = repo_root / target.desired_state_path
    desired_state = validate_target_desired_state(target_name, json.loads(desired_state_path.read_text(encoding="utf-8")))
    promoted = build_target_promotion(target_name, desired_state, candidate)
    output_path.write_text(json.dumps(promoted, indent=2) + "\n", encoding="utf-8")
    pr_body_path.write_text(
        render_promotion_pr_body(
            target_name=target_name,
            release_tag=release_tag,
            candidate=candidate,
            asset_url=resolved["asset_url"],
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        ),
        encoding="utf-8",
    )
    return {
        **candidate,
        "promotion_required": "true" if promoted != desired_state else "false",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--target", required=True)
    resolve.add_argument("--release-tag", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--target", required=True)
    prepare.add_argument("--release-tag", required=True)
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--repo-root", type=Path, default=Path("."))
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--pr-body-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "resolve":
            result = resolve_promotion_request(args.target, args.release_tag)
            write_outputs(result)
            write_environment(result)
        else:
            result = prepare_promotion(
                target_name=args.target,
                release_tag=args.release_tag,
                manifest_path=args.manifest,
                repo_root=args.repo_root,
                output_path=args.output,
                pr_body_path=args.pr_body_output,
            )
            write_outputs(result)
    except (json.JSONDecodeError, OSError, PairedReleaseManifestError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
