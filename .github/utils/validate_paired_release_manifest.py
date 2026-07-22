"""Validate a schema-V2 Paired Release Manifest."""

import re
from typing import Any

TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PRODUCT_IMAGES = {
    "web": "ghcr.io/optiplex331/halligalli-bossyang-web",
    "api": "ghcr.io/optiplex331/halligalli-bossyang-api",
}


class PairedReleaseManifestError(ValueError):
    pass


def validate_paired_release_manifest(manifest: dict[str, Any]) -> dict[str, str]:
    tag, commit = manifest.get("releaseTag"), manifest.get("commit")
    identity, images = manifest.get("runtimeIdentity"), manifest.get("images")
    if manifest.get("schemaVersion") != 2 or not isinstance(tag, str) or not TAG_RE.fullmatch(tag):
        raise PairedReleaseManifestError("manifest requires schema-V2 formal releaseTag")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise PairedReleaseManifestError("manifest requires a full lowercase commit")
    version = tag.removeprefix("v")
    if identity != {"version": version, "commit": commit}:
        raise PairedReleaseManifestError("runtime identity must match release tag and commit")
    if not isinstance(images, dict) or set(images) != set(PRODUCT_IMAGES):
        raise PairedReleaseManifestError("manifest requires complete Web and API images")
    candidate = {"version": version, "commit": commit}
    for role, repository in PRODUCT_IMAGES.items():
        image = images.get(role)
        if not isinstance(image, dict) or image.get("repository") != repository or image.get("tag") != version:
            raise PairedReleaseManifestError(f"manifest requires canonical {role} image identity")
        digest = image.get("digest")
        if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest) or digest == "sha256:" + "0" * 64:
            raise PairedReleaseManifestError(f"{role} image requires immutable digest")
        candidate[f"{role}_repository"] = repository
        candidate[f"{role}_digest"] = digest
    return candidate


def validate_release_evidence(manifest: dict[str, Any], *, expected_tag: str) -> dict[str, str]:
    candidate = validate_paired_release_manifest(manifest)
    if manifest.get("releaseTag") != expected_tag:
        raise PairedReleaseManifestError("manifest does not match the requested release tag")
    return candidate
