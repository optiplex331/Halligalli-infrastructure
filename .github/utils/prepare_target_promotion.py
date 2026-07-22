#!/usr/bin/env python3
"""Prepare one target-scoped promotion from formal Paired Release evidence."""

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

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


def _promotion_candidate(manifest: Any, release_tag: str) -> dict[str, str]:
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != 2:
        raise PromotionError("manifest schema is not supported")
    if manifest.get("releaseTag") != release_tag:
        raise PromotionError("manifest does not match the requested release tag")

    try:
        commit = manifest["commit"]
        digests = {
            role: manifest["images"][role]["digest"] for role in PRODUCT_IMAGES
        }
    except (KeyError, TypeError):
        raise PromotionError("manifest is missing promotion evidence") from None

    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise PromotionError("manifest commit is invalid")
    if any(
        not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest)
        for digest in digests.values()
    ):
        raise PromotionError("manifest image digest is invalid")

    candidate = {
        "version": release_tag.removeprefix("v"),
        "commit": commit,
    }
    for role, repository in PRODUCT_IMAGES.items():
        candidate[f"{role}_repository"] = repository
        candidate[f"{role}_digest"] = digests[role]
    return candidate


def _promotion_request(target_name: str, release_tag: str) -> dict[str, str]:
    target = TARGETS.get(target_name)
    if target is None:
        raise PromotionError(f"target must be one of: {', '.join(TARGETS)}")
    if not TAG_RE.fullmatch(release_tag):
        raise PromotionError("release_tag must match vX.Y.Z")
    return {
        "desired_state_path": target["desired_state_path"],
        "promotion_branch": target["promotion_branch"],
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


def _prepare_resolved_promotion(
    *,
    request: dict[str, str],
    target_name: str,
    release_tag: str,
    manifest: Any,
    desired_state: Any,
) -> dict[str, Any]:
    candidate = _promotion_candidate(manifest, release_tag)
    promoted = _build_target_promotion(target_name, desired_state, candidate)
    return {
        "desired_state": promoted,
        "pr_body": _render_pr_body(
            target_name=target_name,
            release_tag=release_tag,
            candidate=candidate,
        ),
        "outputs": {
            **request,
            "commit": candidate["commit"],
            "web_image": (
                f'{candidate["web_repository"]}@{candidate["web_digest"]}'
            ),
            "api_image": (
                f'{candidate["api_repository"]}@{candidate["api_digest"]}'
            ),
            "promotion_required": "true" if promoted != desired_state else "false",
        },
    }


def prepare_promotion(
    *, target_name: str, release_tag: str, manifest: Any, desired_state: Any
) -> dict[str, Any]:
    return _prepare_resolved_promotion(
        request=_promotion_request(target_name, release_tag),
        target_name=target_name,
        release_tag=release_tag,
        manifest=manifest,
        desired_state=desired_state,
    )


def write_outputs(values: dict[str, str]) -> None:
    command_file_path = os.environ.get("GITHUB_OUTPUT")
    if command_file_path:
        with Path(command_file_path).open("a", encoding="utf-8") as command_file:
            for name, value in values.items():
                command_file.write(f"{name}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--pr-body-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        request = _promotion_request(args.target, args.release_tag)
        desired_state_path = args.repo_root / request["desired_state_path"]
        promotion = _prepare_resolved_promotion(
            request=request,
            target_name=args.target,
            release_tag=args.release_tag,
            manifest=json.loads(args.manifest.read_text(encoding="utf-8")),
            desired_state=json.loads(desired_state_path.read_text(encoding="utf-8")),
        )
        if promotion["outputs"]["promotion_required"] == "true":
            desired_state_path.write_text(
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
