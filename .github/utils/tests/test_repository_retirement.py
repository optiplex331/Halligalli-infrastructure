"""Tests for retired infrastructure source boundaries."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


class RepositoryRetirementTest(unittest.TestCase):
    def test_no_retired_container_apps_sources_are_tracked(self) -> None:
        retired_prefixes = ("terraform/azure-production/",)
        retired_paths = {
            ".github/utils/write_azure_terraform_config.py",
            ".github/utils/tests/test_write_azure_terraform_config.py",
            "docs/operations/azure-production-infrastructure.md",
        }

        remaining = [
            path
            for path in tracked_paths()
            if path in retired_paths or path.startswith(retired_prefixes)
        ]

        self.assertEqual([], remaining)

    def test_active_docs_do_not_reference_retired_terraform_root(self) -> None:
        active_documents = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "docs" / "operations" / "aks.md",
            REPO_ROOT / "terraform" / "aks" / "README.md",
        ]

        for active_document in active_documents:
            self.assertNotIn(
                "terraform/azure-production/",
                active_document.read_text(encoding="utf-8"),
                f"active documentation references the retired Terraform root: {active_document}",
            )


if __name__ == "__main__":
    unittest.main()
