#!/usr/bin/env python3
"""Prepare one target-scoped promotion from formal Paired Release evidence."""

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

PRODUCT_REPOSITORY = "optiplex331/Halligalli-BossYang"
TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PRODUCT_IMAGES = {
    "web": "ghcr.io/optiplex331/halligalli-bossyang-web",
    "api": "ghcr.io/optiplex331/halligalli-bossyang-api",
}
TARGETS = {
    "aks": {
        "desired_state_path": "targets/aks/gitops/values/halligalli.values.json",
        "promotion_branch": "automation/aks-promotion",
        "commit_scope": "aks",
        "display_name": "AKS Deployment Target",
    },
    "container-apps": {
        "desired_state_path": "targets/container-apps/desired-state.json",
        "promotion_branch": "automation/container-apps-promotion",
        "commit_scope": "container-apps",
        "display_name": "container-apps Live Demo Environment",
    },
}


class PromotionError(ValueError):
    pass


def _validate_release_evidence(manifest: Any, expected_tag: str) -> dict[str, str]:
    if not isinstance(manifest, dict):
        raise PromotionError("manifest must be a JSON object")

    tag = manifest.get("releaseTag")
    commit = manifest.get("commit")
    identity = manifest.get("runtimeIdentity")
    images = manifest.get("images")
    if (
        manifest.get("schemaVersion") != 2
        or not isinstance(tag, str)
        or not TAG_RE.fullmatch(tag)
    ):
        raise PromotionError("manifest requires schema-V2 formal releaseTag")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise PromotionError("manifest requires a full lowercase commit")

    version = tag.removeprefix("v")
    if identity != {"version": version, "commit": commit}:
        raise PromotionError("runtime identity must match release tag and commit")
    if not isinstance(images, dict) or set(images) != set(PRODUCT_IMAGES):
        raise PromotionError("manifest requires complete Web and API images")

    candidate = {"version": version, "commit": commit}
    for role, repository in PRODUCT_IMAGES.items():
        image = images.get(role)
        if (
            not isinstance(image, dict)
            or image.get("repository") != repository
            or image.get("tag") != version
        ):
            raise PromotionError(f"manifest requires canonical {role} image identity")
        digest = image.get("digest")
        if (
            not isinstance(digest, str)
            or not DIGEST_RE.fullmatch(digest)
            or digest == "sha256:" + "0" * 64
        ):
            raise PromotionError(f"{role} image requires immutable digest")
        candidate[f"{role}_repository"] = repository
        candidate[f"{role}_digest"] = digest
    if tag != expected_tag:
        raise PromotionError("manifest does not match the requested release tag")
    return candidate


def resolve_promotion_request(target_name: str, release_tag: str) -> dict[str, str]:
    target = TARGETS.get(target_name)
    if target is None:
        raise PromotionError(f"target must be one of: {', '.join(TARGETS)}")
    if not TAG_RE.fullmatch(release_tag):
        raise PromotionError("release_tag must match vX.Y.Z")
    return {
        "target": target_name,
        "release_tag": release_tag,
        "desired_state_path": target["desired_state_path"],
        "promotion_branch": target["promotion_branch"],
        "asset_url": f"https://github.com/{PRODUCT_REPOSITORY}/releases/download/{release_tag}/paired-release-manifest.json",
        "commit_message": f"chore({target['commit_scope']}): promote Halligalli {release_tag}",
    }


def _build_target_promotion(
    target_name: str, desired_state: Any, candidate: dict[str, str]
) -> dict[str, Any]:
    if not isinstance(desired_state, dict):
        raise PromotionError("desired state must be a JSON object")
    if (
        target_name == "container-apps"
        and desired_state.get("target") != "container-apps"
    ):
        raise PromotionError(
            "container-apps promotion requires container-apps desired state"
        )
    if target_name == "aks" and "target" in desired_state:
        raise PromotionError("AKS promotion rejects desired state for another target")

    promoted = dict(desired_state)
    for role, key in (("web", "webImage"), ("api", "apiImage")):
        promoted[key] = {
            "repository": candidate[f"{role}_repository"],
            "digest": candidate[f"{role}_digest"],
        }
    promoted["releaseVersion"] = candidate["version"]
    if target_name == "container-apps":
        promoted["releaseCommit"] = candidate["commit"]
        promoted["deploymentEnabled"] = True
    return promoted


def _render_pr_body(
    *, target_name: str, release_tag: str, candidate: dict[str, str]
) -> str:
    target = TARGETS[target_name]
    return f"""## {target["display_name"]} promotion

- Release Tag: `{release_tag}`
- Product commit: `{candidate["commit"]}`
- Web image: `{candidate["web_repository"]}@{candidate["web_digest"]}`
- API image: `{candidate["api_repository"]}@{candidate["api_digest"]}`
- Artifact provenance: verified
- Desired state: `{target["desired_state_path"]}`

Review whether this release should be deployed to the {target["display_name"]} and whether an operational reason blocks it. This Draft PR neither modifies the other Deployment Target nor deploys infrastructure.
"""


def prepare_promotion(
    *, target_name: str, release_tag: str, manifest: Any, desired_state: Any
) -> dict[str, Any]:
    resolve_promotion_request(target_name, release_tag)
    candidate = _validate_release_evidence(manifest, release_tag)
    promoted = _build_target_promotion(target_name, desired_state, candidate)
    return {
        "desired_state": promoted,
        "pr_body": _render_pr_body(
            target_name=target_name,
            release_tag=release_tag,
            candidate=candidate,
        ),
        "outputs": {
            **candidate,
            "promotion_required": "true" if promoted != desired_state else "false",
        },
    }


def write_outputs(values: dict[str, str]) -> None:
    command_file_path = os.environ.get("GITHUB_OUTPUT")
    if command_file_path:
        with Path(command_file_path).open("a", encoding="utf-8") as command_file:
            for name, value in values.items():
                command_file.write(f"{name}={value}\n")


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
        else:
            target = resolve_promotion_request(args.target, args.release_tag)
            promotion = prepare_promotion(
                target_name=args.target,
                release_tag=args.release_tag,
                manifest=json.loads(args.manifest.read_text(encoding="utf-8")),
                desired_state=json.loads(
                    (args.repo_root / target["desired_state_path"]).read_text(
                        encoding="utf-8"
                    )
                ),
            )
            args.output.write_text(
                json.dumps(promotion["desired_state"], indent=2) + "\n",
                encoding="utf-8",
            )
            args.pr_body_output.write_text(promotion["pr_body"], encoding="utf-8")
            result = promotion["outputs"]
            write_outputs(result)
        print(json.dumps(result, sort_keys=True))
    except (json.JSONDecodeError, OSError, PromotionError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
