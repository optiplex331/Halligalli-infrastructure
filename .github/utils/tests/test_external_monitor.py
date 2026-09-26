import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from external_monitor import (  # noqa: E402
    MANIFEST_URL,
    ReleaseIdentityError,
    check_release_identity,
    render_report,
    run_report,
)

ORIGIN = "https://play.example"
COMMIT = "a" * 40
WEB = "sha256:" + "b" * 64
API = "sha256:" + "c" * 64
OTHER = "sha256:" + "d" * 64


def manifest(*, web: str = WEB, api: str = API, version: str = "1.2.3", commit: str = COMMIT) -> dict:
    return {
        "schemaVersion": 2,
        "releaseTag": f"v{version}",
        "commit": commit,
        "images": {"web": {"digest": web}, "api": {"digest": api}},
        "runtimeIdentity": {"version": version, "commit": commit},
    }


def desired_state(*, web: str = WEB, api: str = API) -> dict:
    return {
        "deploymentEnabled": True,
        "webImage": {"repository": "ghcr.io/example/web", "digest": web},
        "apiImage": {"repository": "ghcr.io/example/api", "digest": api},
        "redisImage": {"repository": "docker.io/library/redis", "digest": OTHER},
    }


class ReleaseIdentityMonitorTest(unittest.TestCase):
    def check(self, responses: dict, desired: dict) -> None:
        def fetch(url: str) -> object:
            if url not in responses:
                raise urllib.error.URLError("unreachable")
            return responses[url]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "desired-state.json"
            path.write_text(json.dumps(desired), encoding="utf-8")
            check_release_identity(ORIGIN, path, fetch)

    def responses(self, identity: dict, release: dict) -> dict:
        return {
            f"{ORIGIN}/internal/identity": identity,
            MANIFEST_URL.format(version=identity["version"]): release,
        }

    def test_accepts_running_release_that_matches_desired_state(self) -> None:
        self.check(self.responses({"version": "1.2.3", "commit": COMMIT}, manifest()), desired_state())

    def test_rejects_running_release_that_differs_from_desired_state(self) -> None:
        cases = (
            ("web digest differs", manifest(), desired_state(web=OTHER), "web digest"),
            ("api digest differs", manifest(), desired_state(api=OTHER), "api digest"),
            ("manifest describes another commit", manifest(commit="e" * 40), desired_state(), "does not describe"),
        )
        for name, release, desired, pattern in cases:
            with self.subTest(case=name), self.assertRaisesRegex(ReleaseIdentityError, pattern):
                self.check(self.responses({"version": "1.2.3", "commit": COMMIT}, release), desired)

    def test_rejects_unreachable_or_malformed_identity_and_manifest(self) -> None:
        identity = {"version": "1.2.3", "commit": COMMIT}
        cases = (
            ("identity unreachable", {}, "cannot read running release identity"),
            ("manifest unreachable", {f"{ORIGIN}/internal/identity": identity}, "cannot read Paired Release Manifest"),
            ("identity malformed", {f"{ORIGIN}/internal/identity": {"status": "ok"}}, "string version"),
        )
        for name, responses, pattern in cases:
            with self.subTest(case=name), self.assertRaisesRegex(ReleaseIdentityError, pattern):
                self.check(responses, desired_state())


class ReportOnlyModeTest(unittest.TestCase):
    def test_runs_every_check_and_reports_failures_without_raising(self) -> None:
        calls = []

        def failing() -> None:
            calls.append("https")
            raise RuntimeError("HTTPS returned 503")

        def drifting() -> None:
            calls.append("identity")
            raise ReleaseIdentityError("web digest differs")

        results = run_report([("HTTPS", failing), ("WebSocket", lambda: calls.append("ws")), ("Identity", drifting)])

        self.assertEqual(calls, ["https", "ws", "identity"])
        self.assertEqual([name for name, error in results if error], ["HTTPS", "Identity"])
        report = render_report(ORIGIN, results)
        self.assertIn("| WebSocket | pass |", report)
        self.assertIn("FAIL: ReleaseIdentityError: web digest differs", report)


if __name__ == "__main__":
    unittest.main()
