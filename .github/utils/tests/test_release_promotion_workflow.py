"""Static contract tests for paired, Infrastructure-owned Draft promotion."""
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "promote-release.yml"


class ReleasePromotionWorkflowTest(unittest.TestCase):
    def test_validates_the_complete_pair_before_a_draft_pr(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        for expected in (
            "schema-V2",
            "Paired Release Manifest",
            "Verify Web artifact provenance",
            "Verify API artifact provenance",
            "--deny-self-hosted-runners",
            "Smoke digest-pinned candidate runtime",
            "inspect-dependencies",
            "http://localhost:18000/internal/ready",
            "http://localhost:18080/",
            "python3 -m unittest discover",
            "peter-evans/create-pull-request@5f6978faf089d4d20b00c7766989d076bb2fc7f1",
            "draft: always-true",
        ):
            self.assertIn(expected, workflow)
        for prohibited in (
            "gh pr merge",
            "argocd app sync",
            "kubectl apply",
            "terraform apply",
        ):
            self.assertNotIn(prohibited, workflow)

    def test_permissions_and_draft_only_boundary(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        for expected in ("contents: write", "pull-requests: write", "attestations: read"):
            self.assertIn(expected, workflow)
        self.assertIn("GH_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("draft: always-true", workflow)
        for prohibited in ("gh pr create", "gh pr edit", "gh pr merge", "argocd app sync"):
            self.assertNotIn(prohibited, workflow)

    def test_keeps_aks_promotion_lane_and_one_values_file_scope(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("group: aks-release-promotion", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("VALUES_PATH: gitops/aks/values/halligalli.values.json", workflow)
        self.assertIn("add-paths: ${{ env.VALUES_PATH }}", workflow)
        self.assertIn("Promotion may change only ${VALUES_PATH}", workflow)

    def test_container_apps_has_an_independent_target_scoped_lane(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/promote-container-apps-release.yml").read_text()
        self.assertIn("group: container-apps-release-promotion", workflow)
        self.assertIn("deployment/container-apps/desired-state.json", workflow)
        self.assertIn("--promotion-branch automation/container-apps-promotion", workflow)
        self.assertIn("Paired Release Manifest", workflow)
        self.assertIn("Verify Web artifact provenance", workflow)
        self.assertIn("Verify API artifact provenance", workflow)
        self.assertEqual(workflow.count("GH_TOKEN: ${{ github.token }}"), 2)
        self.assertIn("token: ${{ github.token }}", workflow)
        self.assertIn("add-paths: ${{ env.DESIRED_STATE_PATH }}", workflow)
        self.assertIn("draft: always-true", workflow)
        self.assertNotIn("inspect-pr --input open-promotion-prs.json", workflow)
        self.assertNotIn("gh pr create", workflow)
        self.assertNotIn("gitops/aks", workflow)
        self.assertNotIn("terraform apply", workflow)


if __name__ == "__main__": unittest.main()
