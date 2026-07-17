#!/usr/bin/env python3
"""Prove that every current Ready Web/API Pod runs the selected digest."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}$")
COMPONENTS = {"web": "webImage", "api": "apiImage"}


class PodDigestError(ValueError):
    pass


def terminal_digest(image_id: object) -> str:
    if not isinstance(image_id, str):
        raise PodDigestError("container imageID must be a string")
    match = DIGEST_RE.search(image_id)
    if match is None:
        raise PodDigestError(f"container imageID has no terminal sha256 digest: {image_id!r}")
    return match.group(0)


def expected_digests(values: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for component, key in COMPONENTS.items():
        image = values.get(key)
        digest = image.get("digest") if isinstance(image, dict) else None
        if not isinstance(digest, str) or DIGEST_RE.fullmatch(digest) is None:
            raise PodDigestError(f"desired state requires digest-pinned {key}")
        result[component] = digest
    return result


def verify_pods(payloads: dict[str, dict[str, Any]], expected: dict[str, str]) -> None:
    for component in COMPONENTS:
        pod_list = payloads.get(component)
        items = pod_list.get("items") if isinstance(pod_list, dict) else None
        if not isinstance(items, list):
            raise PodDigestError(f"{component} Pod list is malformed")
        current = []
        for pod in items:
            if not isinstance(pod, dict):
                raise PodDigestError(f"{component} Pod entry is malformed")
            metadata = pod.get("metadata")
            if not isinstance(metadata, dict):
                raise PodDigestError(f"{component} Pod metadata is malformed")
            if not metadata.get("deletionTimestamp"):
                current.append(pod)
        if not current:
            raise PodDigestError(f"no current {component} Pods found")
        for pod in current:
            name = pod["metadata"].get("name", "<unknown>")
            status = pod.get("status")
            if not isinstance(status, dict):
                raise PodDigestError(f"{component} Pod {name} status is malformed")
            conditions = status.get("conditions", [])
            if not isinstance(conditions, list):
                raise PodDigestError(f"{component} Pod {name} conditions are malformed")
            pod_ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions if isinstance(c, dict))
            if status.get("phase") != "Running" or not pod_ready:
                raise PodDigestError(f"{component} Pod {name} is not Running and Ready")
            statuses = status.get("containerStatuses", [])
            if not isinstance(statuses, list):
                raise PodDigestError(f"{component} Pod {name} containerStatuses are malformed")
            business = [entry for entry in statuses if isinstance(entry, dict) and entry.get("name") == component]
            if len(business) != 1 or business[0].get("ready") is not True:
                raise PodDigestError(f"{component} Pod {name} business container is not Ready")
            actual = terminal_digest(business[0].get("imageID"))
            if actual != expected[component]:
                raise PodDigestError(f"{component} Pod {name} runs {actual}, expected {expected[component]}")


def kubectl(*args: str) -> str:
    return subprocess.run(["kubectl", *args], check=True, text=True, capture_output=True).stdout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--values", type=Path, required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--rollout-timeout", default="180s")
    args = parser.parse_args()
    try:
        selected = expected_digests(json.loads(args.values.read_text(encoding="utf-8")))
        payloads: dict[str, dict[str, Any]] = {}
        for component in COMPONENTS:
            kubectl("-n", args.namespace, "rollout", "status", f"deployment/halligalli-{component}", f"--timeout={args.rollout_timeout}")
            payloads[component] = json.loads(kubectl("-n", args.namespace, "get", "pods", "-l", f"app.kubernetes.io/name=halligalli,app.kubernetes.io/component={component}", "-o", "json"))
        verify_pods(payloads, selected)
    except (OSError, json.JSONDecodeError, subprocess.CalledProcessError, PodDigestError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
    print("Every current Ready Halligalli Web/API Pod runs its selected digest.")


if __name__ == "__main__":
    main()
