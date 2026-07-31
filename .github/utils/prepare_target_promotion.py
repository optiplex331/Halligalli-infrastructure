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
        "desired_state_path": "targets/aks/gitops/halligalli/values/aks.values.json",
        "promotion_branch": "automation/aks-promotion",
        "display_name": "AKS Deployment Target",
    },
    "container-apps": {
        "desired_state_path": "targets/container-apps/desired-state.json",
        "promotion_branch": "automation/container-apps-promotion",
        "display_name": "container-apps Live Demo Environment",
    },
    "k3s": {
        "desired_state_path": "targets/k3s/gitops/runtime/values/experiment.values.json",
        "promotion_branch": "automation/k3s-promotion",
        "display_name": "K3s Deployment Target",
    },
}


class PromotionError(ValueError):
    pass


def _release_selection(manifest: Any, release_tag: str) -> dict[str, Any]:
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != 2:
        raise PromotionError("manifest schema is not supported")
    if manifest.get("releaseTag") != release_tag:
        raise PromotionError("manifest does not match the requested release tag")

    try:
        commit = manifest["commit"]
        images = {}
        for role, repository in PRODUCT_IMAGES.items():
            images[role] = {
                "repository": repository,
                "digest": manifest["images"][role]["digest"],
            }
    except (KeyError, TypeError):
        raise PromotionError("manifest is missing promotion evidence") from None

    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise PromotionError("manifest commit is invalid")
    if any(
        not isinstance(image["digest"], str) or not DIGEST_RE.fullmatch(image["digest"])
        for image in images.values()
    ):
        raise PromotionError("manifest image digest is invalid")

    return {
        "commit": commit,
        "images": images,
    }


def _image_subject(image: dict[str, str]) -> str:
    return f'{image["repository"]}@{image["digest"]}'


def _build_target_promotion(
    target_name: str, desired_state: Any, release: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(desired_state, dict):
        raise PromotionError("desired state must be a JSON object")

    if target_name == "container-apps":
        redis_image = desired_state.get("redisImage")
        if not isinstance(redis_image, dict):
            raise PromotionError("container-apps desired state requires redisImage")
        return {
            "deploymentEnabled": True,
            "webImage": release["images"]["web"],
            "apiImage": release["images"]["api"],
            "redisImage": redis_image,
        }

    promoted = dict(desired_state)
    promoted.update(
        {
            "webImage": release["images"]["web"],
            "apiImage": release["images"]["api"],
        }
    )
    return promoted


def _render_pr_body(
    *, target_name: str, release_tag: str, release: dict[str, Any]
) -> str:
    target = TARGETS[target_name]
    return f"""## {target["display_name"]} promotion

- Release Tag: `{release_tag}`
- Product commit: `{release["commit"]}`
- Web image: `{_image_subject(release["images"]["web"])}`
- API image: `{_image_subject(release["images"]["api"])}`
- Artifact provenance: verified
- Desired state: `{target["desired_state_path"]}`

Review whether this release should be deployed to the {target["display_name"]} and whether an operational reason blocks it. This Draft PR neither modifies the other Deployment Target nor deploys infrastructure.
"""


def prepare_promotion(
    *,
    target_name: str,
    release_tag: str,
    manifest: Any,
    desired_state: Any,
) -> dict[str, Any]:
    """Validate and prepare a target promotion."""

    target = TARGETS.get(target_name)
    if target is None:
        raise PromotionError(f"target must be one of: {', '.join(TARGETS)}")
    if not TAG_RE.fullmatch(release_tag):
        raise PromotionError("release_tag must match vX.Y.Z")

    release = _release_selection(manifest, release_tag)
    promoted = _build_target_promotion(target_name, desired_state, release)
    return {
        "desired_state": promoted,
        "pr_body": _render_pr_body(
            target_name=target_name,
            release_tag=release_tag,
            release=release,
        ),
        "outputs": {
            "desired_state_path": target["desired_state_path"],
            "promotion_branch": target["promotion_branch"],
            "commit_message": f"chore({target_name}): promote Halligalli {release_tag}",
            "commit": release["commit"],
            "web_image": _image_subject(release["images"]["web"]),
            "api_image": _image_subject(release["images"]["api"]),
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
    parser.add_argument("--target", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--pr-body-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        target = TARGETS.get(args.target)
        if target is None:
            raise PromotionError(f"target must be one of: {', '.join(TARGETS)}")

        desired_state_path = Path(target["desired_state_path"])

        promotion = prepare_promotion(
            target_name=args.target,
            release_tag=args.release_tag,
            manifest=json.loads(args.manifest.read_text(encoding="utf-8")),
            desired_state=json.loads(
                desired_state_path.read_text(encoding="utf-8")
            ),
        )
        if promotion["outputs"]["promotion_required"] == "true":
            desired_state_path.write_text(
                json.dumps(promotion["desired_state"], indent=2) + "\n",
                encoding="utf-8",
            )
        args.pr_body_output.write_text(promotion["pr_body"], encoding="utf-8")
        write_outputs(promotion["outputs"])
        print(json.dumps(promotion["outputs"], sort_keys=True))
    except (json.JSONDecodeError, OSError, PromotionError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
