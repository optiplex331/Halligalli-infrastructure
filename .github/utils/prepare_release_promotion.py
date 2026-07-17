#!/usr/bin/env python3
"""Inspect paired release evidence and prepare a narrow GitOps promotion."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from validate_paired_release_manifest import TAG_RE, PairedReleaseManifestError, build_promoted_values, validate_file_to_output

PRODUCT_REPOSITORY = "optiplex331/Halligalli-BossYang"
PROMOTION_BRANCH = "automation/release-promotion"


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


def resolve_promotion_request(release_tag: str, promotion_branch: str = PROMOTION_BRANCH) -> dict[str, str]:
    if not TAG_RE.fullmatch(release_tag):
        raise PairedReleaseManifestError("release_tag must match vX.Y.Z")
    if not re.fullmatch(r"automation/[a-z0-9-]+", promotion_branch):
        raise PairedReleaseManifestError("promotion_branch must be an automation/* branch")
    return {"release_tag": release_tag, "promotion_branch": promotion_branch,
            "asset_url": f"https://github.com/{PRODUCT_REPOSITORY}/releases/download/{release_tag}/paired-release-manifest.json"}


def render_promotion_pr_body(*, release_tag: str, commit: str, web_repository: str, web_digest: str,
                             api_repository: str, api_digest: str, asset_url: str,
                             manifest_sha256: str) -> str:
    return f"""## Paired release evidence

- Release Tag: `{release_tag}`
- Commit: `{commit}`
- Web image: `{web_repository}@{web_digest}`
- API image: `{api_repository}@{api_digest}`
- Paired Release Manifest: {asset_url}
- Manifest SHA-256: `{manifest_sha256}`
- Provenance: both digests matched the exact Product repository, signer workflow, source tag ref, and source commit
- Runtime evidence: digest-pinned Web/API/Redis artifacts became ready and the same-origin API path passed

This Draft PR changes only paired image fields and the display-only release version. It does not merge itself, create cloud resources, or request an Argo CD sync.
"""


def promotion_is_required(promoted_values: dict[str, Any], main_values: dict[str, Any]) -> bool:
    return promoted_values != main_values


def inspect_open_promotion_pr(pull_requests: Any) -> str:
    if not isinstance(pull_requests, list):
        raise PairedReleaseManifestError("promotion PR query must return a list")
    if not pull_requests:
        return ""
    if len(pull_requests) != 1 or not isinstance(pull_requests[0], dict):
        raise PairedReleaseManifestError("promotion lane must have at most one open PR")
    pull_request = pull_requests[0]
    number = pull_request.get("number")
    if pull_request.get("state") != "OPEN" or pull_request.get("isDraft") is not True or not isinstance(number, int) or number <= 0:
        raise PairedReleaseManifestError("existing promotion PR is not an open Draft")
    return str(number)


def inspect_candidate(manifest_path: Path, expected_tag: str, candidate_output: Path) -> None:
    candidate = validate_file_to_output(manifest_path, expected_tag=expected_tag, output_path=candidate_output)
    write_outputs({**candidate, "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()})


def inspect_runtime_dependencies(values_path: Path) -> None:
    values = json.loads(values_path.read_text(encoding="utf-8"))
    redis = values.get("redisImage")
    if not isinstance(redis, dict):
        raise PairedReleaseManifestError("desired state requires redisImage")
    repository, digest = redis.get("repository"), redis.get("digest")
    if not isinstance(repository, str) or not repository or not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise PairedReleaseManifestError("desired state requires digest-pinned redisImage")
    write_outputs({"redis_repository": repository, "redis_digest": digest})


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    resolve = subparsers.add_parser("resolve"); resolve.add_argument("--release-tag", required=True); resolve.add_argument("--promotion-branch", default=PROMOTION_BRANCH)
    inspect = subparsers.add_parser("inspect"); inspect.add_argument("--manifest", type=Path, required=True); inspect.add_argument("--expected-tag", required=True); inspect.add_argument("--candidate-output", type=Path, required=True)
    dependencies = subparsers.add_parser("inspect-dependencies"); dependencies.add_argument("--values", type=Path, required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--candidate", type=Path, required=True); prepare.add_argument("--values", type=Path, required=True); prepare.add_argument("--output", type=Path, required=True)
    assess = subparsers.add_parser("assess-promotion"); assess.add_argument("--promoted-values", type=Path, required=True); assess.add_argument("--main-values", type=Path, required=True)
    pr_state = subparsers.add_parser("inspect-pr"); pr_state.add_argument("--input", type=Path, required=True)
    render = subparsers.add_parser("render-pr")
    for name in ("--release-tag", "--commit", "--web-repository", "--web-digest", "--api-repository", "--api-digest", "--asset-url", "--manifest-sha256"):
        render.add_argument(name, required=True)
    render.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "resolve":
            request = resolve_promotion_request(args.release_tag, args.promotion_branch); write_outputs(request); write_environment(request)
        elif args.command == "inspect": inspect_candidate(args.manifest, args.expected_tag, args.candidate_output)
        elif args.command == "inspect-dependencies": inspect_runtime_dependencies(args.values)
        elif args.command == "prepare":
            candidate = json.loads(args.candidate.read_text()); args.output.write_text(json.dumps(build_promoted_values(json.loads(args.values.read_text()), candidate), indent=2) + "\n"); write_outputs(candidate)
        elif args.command == "assess-promotion": write_outputs({"promotion_required": "true" if promotion_is_required(json.loads(args.promoted_values.read_text()), json.loads(args.main_values.read_text())) else "false"})
        elif args.command == "inspect-pr": write_outputs({"number": inspect_open_promotion_pr(json.loads(args.input.read_text()))})
        else: args.output.write_text(render_promotion_pr_body(release_tag=args.release_tag, commit=args.commit, web_repository=args.web_repository, web_digest=args.web_digest, api_repository=args.api_repository, api_digest=args.api_digest, asset_url=args.asset_url, manifest_sha256=args.manifest_sha256))
    except (json.JSONDecodeError, OSError, PairedReleaseManifestError) as error:
        print(error, file=sys.stderr); sys.exit(1)


if __name__ == "__main__": main()
