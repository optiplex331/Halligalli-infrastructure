"""Focused static checks for the disposable observability proof stack."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
GITOPS_ROOT = REPO_ROOT / "gitops" / "aks"
APPLICATION_PATH = GITOPS_ROOT / "applications" / "halligalli-observability.application.json"
VALUES_PATH = GITOPS_ROOT / "values" / "halligalli-observability.values.json"
CHART_PATH = GITOPS_ROOT / "chart" / "halligalli-observability"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class ObservabilityGitopsDesiredStateTest(unittest.TestCase):
    def test_observability_application_uses_the_closed_infra_chart(self) -> None:
        application = load_json(APPLICATION_PATH)

        self.assertEqual(application["metadata"]["name"], "halligalli-observability")
        self.assertEqual(application["spec"]["destination"]["namespace"], "halligalli-observability")
        chart_source = next(source for source in application["spec"]["sources"] if "path" in source)
        self.assertEqual(chart_source["path"], "gitops/aks/chart/halligalli-observability")
        self.assertEqual(chart_source["helm"]["valueFiles"], ["$values/gitops/aks/values/halligalli-observability.values.json"])

    def test_render_is_one_ephemeral_four_component_stack(self) -> None:
        rendered = subprocess.run(
            ["helm", "template", "halligalli-observability", str(CHART_PATH), "--values", str(VALUES_PATH)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

        self.assertEqual(rendered.count("kind: Deployment\n"), 4)
        self.assertEqual(rendered.count("kind: Service\n"), 4)
        self.assertIn("name: halligalli-observability-prometheus", rendered)
        self.assertIn("name: halligalli-observability-grafana", rendered)
        self.assertIn("name: halligalli-observability-collector", rendered)
        self.assertIn("name: halligalli-observability-tempo", rendered)
        self.assertIn("mountPath: /etc/grafana/provisioning/datasources", rendered)
        self.assertIn("mountPath: /etc/grafana/dashboards", rendered)
        self.assertIn("targets: ['halligalli-api.halligalli.svc.cluster.local:8000']", rendered)
        self.assertIn("url: http://halligalli-observability-prometheus:9090", rendered)
        self.assertIn("endpoint: http://halligalli-observability-tempo:4318", rendered)
        self.assertIn("tempo:3200", rendered)
        self.assertIn("emptyDir: {}", rendered)
        self.assertNotIn("PersistentVolumeClaim", rendered)
        self.assertNotIn("Alertmanager", rendered)
        self.assertNotIn("remote_write", rendered)
        self.assertIn("name: halligalli-observability-default-deny", rendered)


if __name__ == "__main__":
    unittest.main()
