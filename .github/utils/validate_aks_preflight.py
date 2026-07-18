#!/usr/bin/env python3
"""Validate structured inputs for the approval-gated AKS preflight."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REGION = "westeurope"
NODE_SKU = "Standard_D4ls_v6"
REQUIRED_VCPUS = 8
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^1\.[0-9]{2}\.[0-9]+$")
BACKEND_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class AksPreflightError(ValueError):
    """Raised when an AKS preflight input is not safe to use."""


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AksPreflightError(f"Could not read JSON from {path}: {error}") from error
    if not isinstance(value, dict):
        raise AksPreflightError(f"Expected a JSON object in {path}.")
    return value


def validate_subscription(account: dict[str, Any], expected_id: str) -> dict[str, str]:
    if account.get("id") != expected_id:
        raise AksPreflightError("The selected Azure subscription does not match AZURE_SUBSCRIPTION_ID.")
    if account.get("state") != "Enabled":
        raise AksPreflightError("The selected Azure subscription is not enabled.")
    return {"id": expected_id, "name": str(account.get("name", ""))}


def validate_sku(payload: dict[str, Any]) -> None:
    values = payload.get("value")
    if not isinstance(values, list):
        raise AksPreflightError("Azure Resource SKU data does not contain a value list.")
    matches = []
    for item in values:
        if not isinstance(item, dict) or item.get("name") != NODE_SKU:
            continue
        locations = item.get("locations")
        if isinstance(locations, list) and REGION.casefold() in {
            str(location).casefold() for location in locations
        }:
            matches.append(item)
    if len(matches) != 1:
        raise AksPreflightError(f"Expected exactly one unrestricted {NODE_SKU} entry in {REGION}.")
    if matches[0].get("restrictions"):
        raise AksPreflightError(f"{NODE_SKU} is restricted for the selected subscription in {REGION}.")


def validate_quota(payload: list[Any]) -> None:
    usage: dict[str, tuple[int, int]] = {}
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("name"), dict):
            continue
        name = item["name"].get("value")
        if isinstance(name, str):
            try:
                usage[name] = (int(item.get("currentValue", 0)), int(item.get("limit", 0)))
            except (TypeError, ValueError) as error:
                raise AksPreflightError(f"Azure quota {name} has invalid usage values.") from error
    for name in ("cores", "StandardDlsv6Family"):
        if name not in usage:
            raise AksPreflightError(f"Required Azure quota {name} was not returned.")
        current, limit = usage[name]
        if limit - current < REQUIRED_VCPUS:
            raise AksPreflightError(f"Azure quota {name} has fewer than {REQUIRED_VCPUS} available vCPUs.")


def _strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            result.update(_strings(item))
        return result
    if isinstance(value, dict):
        result = {key for key in value if isinstance(key, str)}
        for item in value.values():
            result.update(_strings(item))
        return result
    return set()


def validate_kubernetes_version(payload: dict[str, Any], target_version: str) -> None:
    if not VERSION_RE.fullmatch(target_version):
        raise AksPreflightError("Kubernetes version must be a full version such as 1.35.5.")
    if target_version not in _strings(payload):
        raise AksPreflightError(f"Kubernetes {target_version} is not offered in {REGION}.")


def _validate_image(state: dict[str, Any], key: str) -> None:
    image = state.get(key)
    if not isinstance(image, dict):
        raise AksPreflightError(f"AKS desired state requires {key}.")
    repository, digest = image.get("repository"), image.get("digest")
    if (
        not isinstance(repository, str)
        or not repository
        or not isinstance(digest, str)
        or not DIGEST_RE.fullmatch(digest)
    ):
        raise AksPreflightError(f"AKS desired state {key} must be digest pinned.")


def validate_desired_state(state: dict[str, Any]) -> None:
    for key in ("webImage", "apiImage", "redisImage"):
        _validate_image(state, key)
    if not isinstance(state.get("releaseVersion"), str) or not state["releaseVersion"]:
        raise AksPreflightError("AKS desired state requires releaseVersion.")
    ingress = state.get("ingress")
    if not isinstance(ingress, dict) or not ingress.get("host") or not ingress.get("tlsSecretName"):
        raise AksPreflightError("AKS desired state requires ingress host and TLS Secret name.")


def write_backend_config(path: Path, organization: str, workspace: str) -> None:
    if not BACKEND_NAME_RE.fullmatch(organization):
        raise AksPreflightError("HCP Terraform organization contains unsupported characters.")
    if not BACKEND_NAME_RE.fullmatch(workspace):
        raise AksPreflightError("HCP Terraform workspace contains unsupported characters.")
    path.write_text(
        f'organization = "{organization}"\n\nworkspaces {{\n  name = "{workspace}"\n}}\n',
        encoding="utf-8",
    )


def load_array(path: Path) -> list[Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AksPreflightError(f"Could not read JSON from {path}: {error}") from error
    if not isinstance(value, list):
        raise AksPreflightError(f"Expected a JSON array in {path}.")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-subscription", required=True)
    parser.add_argument("--kubernetes-version", required=True)
    parser.add_argument("--subscription", type=Path, required=True)
    parser.add_argument("--resource-skus", type=Path, required=True)
    parser.add_argument("--quota", type=Path, required=True)
    parser.add_argument("--aks-versions", type=Path, required=True)
    parser.add_argument("--desired-state", type=Path, required=True)
    parser.add_argument("--terraform-organization", required=True)
    parser.add_argument("--terraform-workspace", required=True)
    parser.add_argument("--backend-output", type=Path, required=True)
    args = parser.parse_args()

    subscription = validate_subscription(load_object(args.subscription), args.expected_subscription)
    validate_sku(load_object(args.resource_skus))
    validate_quota(load_array(args.quota))
    validate_kubernetes_version(load_object(args.aks_versions), args.kubernetes_version)
    desired_state = load_object(args.desired_state)
    validate_desired_state(desired_state)
    write_backend_config(args.backend_output, args.terraform_organization, args.terraform_workspace)
    print(
        json.dumps(
            {
                "subscription": subscription,
                "region": REGION,
                "nodeSku": NODE_SKU,
                "requiredVcpus": REQUIRED_VCPUS,
                "kubernetesVersion": args.kubernetes_version,
                "releaseVersion": desired_state["releaseVersion"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except AksPreflightError as error:
        raise SystemExit(str(error)) from error
