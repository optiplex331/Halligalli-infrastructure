#!/usr/bin/env python3
"""Generate private Terraform config files for AKS Validation Run operations."""

from __future__ import annotations

import json
import os
from pathlib import Path


ENVIRONMENT_NAME = "local AKS Validation Run operation environment"


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Set {name} in the {ENVIRONMENT_NAME}.")
    return value


def optional(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def put_if_present(config: dict[str, object], key: str, value: object | None) -> None:
    if value is not None:
        config[key] = value


def reject_if_present(name: str) -> None:
    if optional(name) is not None:
        raise SystemExit(f"{name} is not supported for the AKS Deployment Target.")


def main() -> None:
    operation = required("HALLIGALLI_AKS_TERRAFORM_OPERATION")
    if operation not in {"plan", "apply", "destroy"}:
        raise SystemExit("HALLIGALLI_AKS_TERRAFORM_OPERATION must be plan, apply, or destroy.")

    backend_path = Path(required("TERRAFORM_BACKEND_CONFIG_PATH"))
    tfvars_path = Path(required("TERRAFORM_TFVARS_JSON_PATH"))

    organization = required("HCP_TERRAFORM_ORGANIZATION")
    workspace = required("HCP_TERRAFORM_WORKSPACE")

    reject_if_present("HALLIGALLI_AKS_ENABLE_CONTAINER_INSIGHTS")
    reject_if_present("HALLIGALLI_AKS_LOG_ANALYTICS_RETENTION_DAYS")

    backend_path.write_text(
        f'organization = "{organization}"\n\nworkspaces {{\n  name = "{workspace}"\n}}\n',
        encoding="utf-8",
    )

    config: dict[str, object] = {
        "domain_name": required("HALLIGALLI_AKS_DOMAIN_NAME"),
    }

    put_if_present(config, "ingress_subdomain", optional("HALLIGALLI_AKS_INGRESS_SUBDOMAIN"))
    put_if_present(config, "resource_group_name", optional("HALLIGALLI_AKS_RESOURCE_GROUP_NAME"))
    put_if_present(config, "aks_cluster_name", optional("HALLIGALLI_AKS_CLUSTER_NAME"))
    put_if_present(
        config,
        "node_resource_group_name",
        optional("HALLIGALLI_AKS_NODE_RESOURCE_GROUP_NAME"),
    )
    put_if_present(config, "dns_prefix", optional("HALLIGALLI_AKS_DNS_PREFIX"))
    put_if_present(config, "kubernetes_version", optional("HALLIGALLI_AKS_KUBERNETES_VERSION"))

    tfvars_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote Terraform backend config to {backend_path}")
    print(f"Wrote Terraform tfvars JSON to {tfvars_path}")


if __name__ == "__main__":
    main()
