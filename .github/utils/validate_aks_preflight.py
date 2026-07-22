#!/usr/bin/env python3
"""Validate structured inputs for the approval-gated AKS preflight."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


VERSION_RE = re.compile(r"^1\.[0-9]{2}\.[0-9]+$")
BACKEND_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
TARGET_KEYS = {"region", "nodeSku", "nodeCount"}


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


def _require_exact_keys(value: dict[str, Any], expected: set[str], context: str) -> None:
    missing = expected - value.keys()
    extra = value.keys() - expected
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing {', '.join(sorted(missing))}")
        if extra:
            details.append(f"unsupported {', '.join(sorted(extra))}")
        raise AksPreflightError(f"{context} has an invalid closed contract: {'; '.join(details)}.")


def load_target_facts(path: Path) -> dict[str, Any]:
    """Load the concrete target facts from Terraform's native JSON configuration."""
    document = load_object(path)
    _require_exact_keys(document, {"locals"}, "AKS Terraform target")
    locals_block = document["locals"]
    if not isinstance(locals_block, dict):
        raise AksPreflightError("AKS Terraform target locals must be an object.")
    _require_exact_keys(locals_block, {"aks_target"}, "AKS Terraform target locals")
    target = locals_block["aks_target"]
    if not isinstance(target, dict):
        raise AksPreflightError("AKS Terraform target facts must be an object.")
    _require_exact_keys(target, TARGET_KEYS, "AKS Terraform target facts")

    for key in ("region", "nodeSku"):
        if not isinstance(target[key], str) or not target[key]:
            raise AksPreflightError(f"AKS Terraform target {key} must be a non-empty string.")
    if not isinstance(target["nodeCount"], int) or isinstance(target["nodeCount"], bool) or target["nodeCount"] < 1:
        raise AksPreflightError("AKS Terraform target nodeCount must be a positive integer.")
    return target


def validate_subscription(account: dict[str, Any], expected_id: str) -> dict[str, str]:
    if account.get("id") != expected_id:
        raise AksPreflightError("The selected Azure subscription does not match AZURE_SUBSCRIPTION_ID.")
    if account.get("state") != "Enabled":
        raise AksPreflightError("The selected Azure subscription is not enabled.")
    return {"id": expected_id, "name": str(account.get("name", ""))}


def validate_sku(payload: dict[str, Any], target: dict[str, Any]) -> tuple[str, int]:
    values = payload.get("value")
    if not isinstance(values, list):
        raise AksPreflightError("Azure Resource SKU data does not contain a value list.")
    matches = []
    for item in values:
        if not isinstance(item, dict) or item.get("name") != target["nodeSku"]:
            continue
        locations = item.get("locations")
        if isinstance(locations, list) and target["region"].casefold() in {
            str(location).casefold() for location in locations
        }:
            matches.append(item)
    if len(matches) != 1:
        raise AksPreflightError(
            f"Expected exactly one unrestricted {target['nodeSku']} entry in {target['region']}."
        )
    if matches[0].get("restrictions"):
        raise AksPreflightError(
            f"{target['nodeSku']} is restricted for the selected subscription in {target['region']}."
        )
    quota_family = matches[0].get("family")
    if not isinstance(quota_family, str) or not quota_family:
        raise AksPreflightError(f"{target['nodeSku']} does not report a quota family.")
    capabilities = matches[0].get("capabilities")
    if not isinstance(capabilities, list):
        raise AksPreflightError(f"{target['nodeSku']} does not report SKU capabilities.")
    vcpu_values = [
        item.get("value")
        for item in capabilities
        if isinstance(item, dict) and item.get("name") == "vCPUs"
    ]
    if len(vcpu_values) != 1:
        raise AksPreflightError(f"{target['nodeSku']} does not report exactly one vCPU capacity.")
    try:
        vcpus_per_node = int(vcpu_values[0])
    except (TypeError, ValueError) as error:
        raise AksPreflightError(f"{target['nodeSku']} reports an invalid vCPU capacity.") from error
    if vcpus_per_node < 1:
        raise AksPreflightError(f"{target['nodeSku']} reports an invalid vCPU capacity.")
    return quota_family, vcpus_per_node


def validate_quota(
    payload: list[Any],
    target: dict[str, Any],
    *,
    quota_family: str,
    vcpus_per_node: int,
) -> None:
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
    required_vcpus = target["nodeCount"] * vcpus_per_node
    for name in ("cores", quota_family):
        if name not in usage:
            raise AksPreflightError(f"Required Azure quota {name} was not returned.")
        current, limit = usage[name]
        if limit - current < required_vcpus:
            raise AksPreflightError(
                f"Azure quota {name} has fewer than {required_vcpus} available vCPUs."
            )


def validate_kubernetes_version(
    payload: dict[str, Any], target_version: str, target: dict[str, Any]
) -> None:
    if not VERSION_RE.fullmatch(target_version):
        raise AksPreflightError("Kubernetes version must be a full version such as 1.35.5.")
    values = payload.get("values")
    if not isinstance(values, list):
        raise AksPreflightError("Azure Kubernetes version data does not contain a value list.")
    offered_patches: set[str] = set()
    for version in values:
        if not isinstance(version, dict) or not isinstance(version.get("version"), str):
            raise AksPreflightError("Azure Kubernetes version entry is malformed.")
        patch_versions = version.get("patchVersions")
        if not isinstance(patch_versions, dict):
            raise AksPreflightError("Azure Kubernetes version entry is malformed.")
        offered_patches.update(patch for patch in patch_versions if isinstance(patch, str))
    if target_version not in offered_patches:
        raise AksPreflightError(
            f"Kubernetes {target_version} is not offered in {target['region']}."
        )


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
    subparsers = parser.add_subparsers(dest="command", required=True)

    target_field = subparsers.add_parser("target-field")
    target_field.add_argument("--terraform-target", type=Path, required=True)
    target_field.add_argument(
        "--name", choices=("region", "nodeSku", "nodeCount"), required=True
    )

    validate = subparsers.add_parser("validate")
    validate.add_argument("--terraform-target", type=Path, required=True)
    validate.add_argument("--expected-subscription", required=True)
    validate.add_argument("--kubernetes-version", required=True)
    validate.add_argument("--subscription", type=Path, required=True)
    validate.add_argument("--resource-skus", type=Path, required=True)
    validate.add_argument("--quota", type=Path, required=True)
    validate.add_argument("--aks-versions", type=Path, required=True)
    validate.add_argument("--terraform-organization", required=True)
    validate.add_argument("--terraform-workspace", required=True)
    validate.add_argument("--backend-output", type=Path, required=True)
    args = parser.parse_args()

    target = load_target_facts(args.terraform_target)
    if args.command == "target-field":
        print(target[args.name])
        return

    subscription = validate_subscription(load_object(args.subscription), args.expected_subscription)
    quota_family, vcpus_per_node = validate_sku(load_object(args.resource_skus), target)
    validate_quota(
        load_array(args.quota),
        target,
        quota_family=quota_family,
        vcpus_per_node=vcpus_per_node,
    )
    validate_kubernetes_version(load_object(args.aks_versions), args.kubernetes_version, target)
    write_backend_config(args.backend_output, args.terraform_organization, args.terraform_workspace)
    print(
        json.dumps(
            {
                "subscription": subscription,
                "region": target["region"],
                "nodeSku": target["nodeSku"],
                "nodeCount": target["nodeCount"],
                "requiredVcpus": target["nodeCount"] * vcpus_per_node,
                "kubernetesVersion": args.kubernetes_version,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except AksPreflightError as error:
        raise SystemExit(str(error)) from error
