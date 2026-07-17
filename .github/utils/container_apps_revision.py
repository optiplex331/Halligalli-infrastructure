#!/usr/bin/env python3
"""Validate desired state and render one revision-safe Container Apps candidate."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class ContainerAppsRevisionError(ValueError):
    pass


def _image(state: dict[str, Any], key: str) -> str:
    value = state.get(key)
    if not isinstance(value, dict):
        raise ContainerAppsRevisionError(f"desired state requires {key}")
    repository, digest = value.get("repository"), value.get("digest")
    if not isinstance(repository, str) or not repository or not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
        raise ContainerAppsRevisionError(f"{key} must be digest pinned")
    return f"{repository}@{digest}"


def validate_desired_state(state: dict[str, Any]) -> dict[str, str]:
    if state.get("schemaVersion") != 1 or state.get("target") != "container-apps":
        raise ContainerAppsRevisionError("desired state must target container-apps schemaVersion 1")
    if state.get("deploymentEnabled") is not True:
        raise ContainerAppsRevisionError("desired state is a non-deployable bootstrap placeholder")
    version, commit = state.get("releaseVersion"), state.get("releaseCommit")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise ContainerAppsRevisionError("desired state requires a releaseVersion")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise ContainerAppsRevisionError("desired state requires a full releaseCommit")
    return {
        "version": version,
        "commit": commit,
        "web_image": _image(state, "webImage"),
        "api_image": _image(state, "apiImage"),
        "redis_image": _image(state, "redisImage"),
    }


def render_candidate(state: dict[str, Any], suffix: str) -> dict[str, Any]:
    release = validate_desired_state(state)
    if not re.fullmatch(r"r[0-9]+-[0-9a-f]{7}", suffix):
        raise ContainerAppsRevisionError("revision suffix must be r<run>-<commit7>")
    return {
        "properties": {
            "template": {
                "revisionSuffix": suffix,
                "containers": [
                    {
                        "name": "web",
                        "image": release["web_image"],
                        "env": [{"name": "HALLIGALLI_API_ORIGIN", "value": "http://localhost:8000"}],
                        "resources": {"cpu": 0.12, "memory": "0.25Gi"},
                    },
                    {
                        "name": "api",
                        "image": release["api_image"],
                        "env": [{"name": "HALLIGALLI_REDIS_URL", "value": "redis://localhost:6379/0"}],
                        "resources": {"cpu": 0.26, "memory": "0.5Gi"},
                    },
                    {
                        "name": "redis",
                        "image": release["redis_image"],
                        "args": ["redis-server", "--save", "", "--appendonly", "no"],
                        "resources": {"cpu": 0.12, "memory": "0.25Gi"},
                    },
                ],
                "scale": {"minReplicas": 1, "maxReplicas": 1},
            }
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("desired_state", type=Path)
    parser.add_argument("--revision-suffix", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    state = json.loads(args.desired_state.read_text(encoding="utf-8"))
    args.output.write_text(json.dumps(render_candidate(state, args.revision_suffix), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
