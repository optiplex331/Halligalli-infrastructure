"""Build one target-scoped promotion from formal Paired Release evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from validate_paired_release_manifest import (
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


@dataclass(frozen=True)
class PreparedPromotion:
    desired_state: dict[str, Any]
    pr_body: str
    outputs: dict[str, str]


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


def _validate_current_target(target_name: str, desired_state: Any) -> dict[str, Any]:
    if not isinstance(desired_state, dict):
        raise PairedReleaseManifestError("desired state must be a JSON object")
    if target_name == "container-apps" and desired_state.get("target") != "container-apps":
        raise PairedReleaseManifestError("container-apps promotion requires container-apps desired state")
    if target_name == "aks" and "target" in desired_state:
        raise PairedReleaseManifestError("AKS promotion rejects desired state for another target")
    return desired_state


def _build_target_promotion(
    target_name: str, desired_state: Any, candidate: dict[str, str]
) -> dict[str, Any]:
    promoted = dict(_validate_current_target(target_name, desired_state))
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


def _render_pr_body(*, target_name: str, release_tag: str, candidate: dict[str, str]) -> str:
    target = TARGETS[target_name]
    return f"""## {target.display_name} promotion

- Release Tag: `{release_tag}`
- Product commit: `{candidate['commit']}`
- Web image: `{candidate['web_repository']}@{candidate['web_digest']}`
- API image: `{candidate['api_repository']}@{candidate['api_digest']}`
- Artifact provenance: verified
- Desired state: `{target.desired_state_path}`

Review whether this release should be deployed to the {target.display_name} and whether an operational reason blocks it. This Draft PR neither modifies the other Deployment Target nor deploys infrastructure.
"""


def prepare_promotion(
    *, target_name: str, release_tag: str, manifest: Any, desired_state: Any
) -> PreparedPromotion:
    resolve_promotion_request(target_name, release_tag)
    candidate = validate_release_evidence(manifest, expected_tag=release_tag)
    promoted = _build_target_promotion(target_name, desired_state, candidate)
    return PreparedPromotion(
        desired_state=promoted,
        pr_body=_render_pr_body(
            target_name=target_name,
            release_tag=release_tag,
            candidate=candidate,
        ),
        outputs={
            **candidate,
            "promotion_required": "true" if promoted != desired_state else "false",
        },
    )
