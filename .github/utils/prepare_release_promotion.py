#!/usr/bin/env python3
"""GitHub Actions adapter for target-scoped release promotion."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from release_promotion import (
    PairedReleaseManifestError,
    prepare_promotion,
    resolve_promotion_request,
)


def write_environment(values: dict[str, str]) -> None:
    command_file_path = os.environ.get("GITHUB_ENV")
    if command_file_path:
        with Path(command_file_path).open("a", encoding="utf-8") as command_file:
            for name, value in values.items():
                command_file.write(f"{name.upper()}={value}\n")


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
            write_environment(result)
        else:
            target = resolve_promotion_request(args.target, args.release_tag)
            promotion = prepare_promotion(
                target_name=args.target,
                release_tag=args.release_tag,
                manifest=json.loads(args.manifest.read_text(encoding="utf-8")),
                desired_state=json.loads(
                    (args.repo_root / target["desired_state_path"]).read_text(encoding="utf-8")
                ),
            )
            args.output.write_text(json.dumps(promotion.desired_state, indent=2) + "\n", encoding="utf-8")
            args.pr_body_output.write_text(promotion.pr_body, encoding="utf-8")
            result = promotion.outputs
            write_outputs(result)
        print(json.dumps(result, sort_keys=True))
    except (json.JSONDecodeError, OSError, PairedReleaseManifestError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
