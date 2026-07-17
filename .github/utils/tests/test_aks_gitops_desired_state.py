"""Tests for AKS Deployment Target GitOps desired state."""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
GITOPS_ROOT = REPO_ROOT / "gitops" / "aks"
APPLICATION_PATH = GITOPS_ROOT / "applications" / "halligalli.application.json"
VALUES_PATH = GITOPS_ROOT / "values" / "halligalli.values.json"
CHART_PATH = GITOPS_ROOT / "chart" / "halligalli"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for entry in value for item in string_values(entry)]
    if isinstance(value, dict):
        return [item for entry in value.values() for item in string_values(entry)]
    return []


class AksGitopsDesiredStateTest(unittest.TestCase):
    def test_argocd_application_uses_infra_owned_chart_and_values(self) -> None:
        application = load_json(APPLICATION_PATH)

        self.assertEqual(application["apiVersion"], "argoproj.io/v1alpha1")
        self.assertEqual(application["kind"], "Application")
        self.assertEqual(application["metadata"]["namespace"], "argocd")
        self.assertEqual(application["metadata"]["name"], "halligalli")

        sources = application["spec"]["sources"]
        chart_source = next(
            source
            for source in sources
            if source.get("path") == "gitops/aks/chart/halligalli"
        )
        values_source = next(source for source in sources if source.get("ref") == "values")

        self.assertEqual(chart_source["repoURL"], "https://github.com/optiplex331/Halligalli-infrastructure.git")
        self.assertEqual(chart_source["targetRevision"], "main")
        self.assertEqual(chart_source["helm"]["releaseName"], "halligalli")
        self.assertEqual(
            chart_source["helm"]["valueFiles"],
            ["$values/gitops/aks/values/halligalli.values.json"],
        )

        self.assertEqual(values_source["repoURL"], "https://github.com/optiplex331/Halligalli-infrastructure.git")
        self.assertEqual(values_source["targetRevision"], "main")
        self.assertEqual(application["spec"]["destination"]["namespace"], "halligalli")
        self.assertIn("CreateNamespace=true", application["spec"]["syncPolicy"]["syncOptions"])
        self.assertTrue(application["spec"]["syncPolicy"]["automated"]["selfHeal"])

    def test_aks_chart_is_owned_by_gitops_desired_state(self) -> None:
        expected_files = [
            CHART_PATH / "Chart.yaml",
            CHART_PATH / "values.yaml",
            CHART_PATH / "values.schema.json",
            CHART_PATH / "templates" / "_helpers.tpl",
            CHART_PATH / "templates" / "deployment.yaml",
            CHART_PATH / "templates" / "ingress.yaml",
            CHART_PATH / "templates" / "service.yaml",
            CHART_PATH / "templates" / "serviceaccount.yaml",
            CHART_PATH / "templates" / "pdb.yaml",
            CHART_PATH / "templates" / "networkpolicy.yaml",
            GITOPS_ROOT / "scripts" / "apply-redis-auth-secret.sh",
        ]

        for chart_file in expected_files:
            self.assertTrue(chart_file.is_file(), f"{chart_file} should be tracked with GitOps desired state")

        helpers = (CHART_PATH / "templates" / "_helpers.tpl").read_text(encoding="utf-8")
        deployment = (CHART_PATH / "templates" / "deployment.yaml").read_text(encoding="utf-8")

        self.assertIn(".Values.releaseVersion", helpers)
        self.assertNotIn("releaseIdentity", helpers)
        self.assertNotIn("HALLIGALLI_RELEASE_VERSION", deployment)
        self.assertNotIn("HALLIGALLI_RELEASE_COMMIT", deployment)
        self.assertIn("image digest must match sha256", helpers)
        self.assertIn("automountServiceAccountToken: false", deployment)
        self.assertIn("topologySpreadConstraints", deployment)
        self.assertIn("REDIS_PASSWORD", deployment)
        self.assertIn("/redis-auth/username", deployment)
        self.assertIn("aclfile", deployment)

    def test_rendered_runtime_has_restricted_security_and_network_boundaries(self) -> None:
        values = load_json(VALUES_PATH)
        rendered = subprocess.run(
            [
                "helm", "template", "halligalli", str(CHART_PATH),
                "--values", str(VALUES_PATH),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

        self.assertEqual(rendered.count("kind: NetworkPolicy\n"), 4)
        self.assertIn("name: halligalli-default-deny", rendered)
        self.assertIn("name: halligalli-api", rendered)
        self.assertIn("name: halligalli-redis", rendered)
        self.assertIn("name: halligalli-web", rendered)
        self.assertIn("type: RuntimeDefault", rendered)
        self.assertIn("allowPrivilegeEscalation: false", rendered)
        self.assertIn('drop: ["ALL"]', rendered)
        self.assertIn("readOnlyRootFilesystem: true", rendered)
        self.assertIn("mountPath: /etc/nginx/conf.d", rendered)
        self.assertIn("mountPath: /tmp", rendered)
        self.assertIn("name: nginx-generated-config", rendered)
        self.assertIn("name: nginx-tmp", rendered)
        self.assertIn("name: HALLIGALLI_API_ORIGIN", rendered)
        self.assertIn('value: "http://halligalli-api"', rendered)
        self.assertIn(f'app.kubernetes.io/version: "{values["releaseVersion"]}"', rendered)
        self.assertNotIn("HALLIGALLI_RELEASE_VERSION", rendered)
        self.assertNotIn("HALLIGALLI_RELEASE_COMMIT", rendered)
        self.assertIn("app.kubernetes.io/component: api", rendered)
        self.assertIn("app.kubernetes.io/component: redis", rendered)
        self.assertIn("port: 6379", rendered)
        self.assertIn("k8s-app: kube-dns", rendered)

    def test_redis_secret_helper_and_chart_never_render_a_credential(self) -> None:
        helper = (GITOPS_ROOT / "scripts" / "apply-redis-auth-secret.sh").read_text(encoding="utf-8")
        chart_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (CHART_PATH / "templates").glob("*")
        )

        self.assertIn("HALLIGALLI_OPERATION_APPROVED=1", helper)
        self.assertIn("openssl rand -hex 32", helper)
        self.assertIn("kubectl apply -f -", helper)
        self.assertNotIn("password:", chart_sources)
        self.assertNotIn("stringData:", chart_sources)

        blocked = subprocess.run(
            ["sh", str(GITOPS_ROOT / "scripts" / "apply-redis-auth-secret.sh")],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("HALLIGALLI_OPERATION_APPROVED=1", blocked.stderr)

    def test_halligalli_values_are_digest_pinned_and_same_origin(self) -> None:
        values = load_json(VALUES_PATH)

        self.assertEqual(values["webImage"]["repository"], "ghcr.io/optiplex331/halligalli-bossyang-web")
        self.assertEqual(values["apiImage"]["repository"], "ghcr.io/optiplex331/halligalli-bossyang-api")
        self.assertEqual(values["redisImage"]["repository"], "redis")
        for image_name in ("webImage", "apiImage", "redisImage"):
            self.assertRegex(values[image_name]["digest"], DIGEST_RE)
        self.assertRegex(values["releaseVersion"], r"^[0-9]+\.[0-9]+\.[0-9]+$")
        self.assertNotIn("releaseIdentity", values)
        self.assertEqual(values["redisSecretName"], "halligalli-redis-auth")

        ingress = values["ingress"]
        self.assertEqual(ingress["host"], "proof.invalid")
        self.assertEqual(ingress["tlsSecretName"], "halligalli-proof-tls")

    def test_chart_renders_the_fixed_paired_runtime_topology(self) -> None:
        rendered = subprocess.run(
            [
                "helm", "template", "halligalli", str(CHART_PATH),
                "--values", str(VALUES_PATH),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

        self.assertEqual(rendered.count("kind: Deployment\n"), 3)
        self.assertEqual(rendered.count("kind: Service\n"), 3)
        self.assertEqual(rendered.count("kind: ServiceAccount\n"), 3)
        self.assertEqual(rendered.count("kind: PodDisruptionBudget\n"), 2)
        self.assertIn("name: halligalli-web", rendered)
        self.assertIn("name: halligalli-api", rendered)
        self.assertIn("name: halligalli-redis", rendered)
        self.assertIn("replicas: 2", rendered)
        self.assertIn("type: Recreate", rendered)
        self.assertIn("--workers 1", rendered)
        self.assertIn("whenUnsatisfiable: ScheduleAnyway", rendered)
        self.assertIn("path: /api/v1", rendered)
        self.assertIn("path: /ws/v1", rendered)
        self.assertRegex(rendered, r"path: /api/v1[\s\S]+?name: halligalli-api")
        self.assertRegex(rendered, r"path: /ws/v1[\s\S]+?name: halligalli-api")
        self.assertRegex(rendered, r"path: /\n[\s\S]+?name: halligalli-web")

    def test_chart_rejects_value_escape_hatches(self) -> None:
        for override in (
            "genericEnvironment=aks",
            "webImage.extraEnv.HALLIGALLI_DEBUG=true",
            r"ingress.annotations.nginx\.ingress\.kubernetes\.io/proxy-body-size=1m",
            r"nodeSelector.kubernetes\.io/os=linux",
            "secretEnvFrom[0]=unexpected-secret",
        ):
            with self.subTest(override=override):
                rejected = subprocess.run(
                    [
                        "helm", "template", "halligalli", str(CHART_PATH),
                        "--values", str(VALUES_PATH), "--set", override,
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(rejected.returncode, 0)
                self.assertIn("additional properties", rejected.stderr)

    def test_gitops_state_excludes_legacy_backend_and_floating_image_inputs(self) -> None:
        documents = [load_json(APPLICATION_PATH), load_json(VALUES_PATH)]
        flattened = "\n".join(item for document in documents for item in string_values(document))

        self.assertNotIn("https://github.com/optiplex331/Halligalli-BossYang.git", flattened)
        self.assertNotIn("charts/halligalli", flattened)
        self.assertNotIn("api.halligalli.games", flattened)
        self.assertNotIn("play.halligalli.games", flattened)
        self.assertNotRegex(flattened, r"(?i)(^|[:/@\s])latest($|[:/@\s])")

if __name__ == "__main__":
    unittest.main()
