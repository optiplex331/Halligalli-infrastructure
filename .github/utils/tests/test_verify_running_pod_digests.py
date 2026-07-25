import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_running_pod_digests import (  # noqa: E402
    PodDigestError,
    expected_digests,
    terminal_digest,
    verify_pods,
)


WEB = "sha256:" + "a" * 64
API = "sha256:" + "b" * 64


def pod(component: str, digest: str, *, ready: bool = True, terminating: bool = False) -> dict:
    metadata = {"name": f"halligalli-{component}-abc"}
    if terminating:
        metadata["deletionTimestamp"] = "2026-07-14T00:00:00Z"
    return {
        "metadata": metadata,
        "status": {
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
            "containerStatuses": [
                {"name": component, "ready": ready, "imageID": f"ghcr.io/example/{component}@{digest}"},
                {"name": "sidecar", "ready": False, "imageID": "irrelevant"},
            ],
        },
    }


def payloads(web_items: list[dict], api_items: list[dict]) -> dict:
    return {"web": {"items": web_items}, "api": {"items": api_items}}


def malformed_pod(mutation: str) -> dict:
    value = pod("web", WEB)
    if mutation == "status":
        del value["status"]
    elif mutation == "containerStatuses":
        value["status"]["containerStatuses"] = None
    elif mutation == "business":
        value["status"]["containerStatuses"][0]["name"] = "other"
    elif mutation == "imageID":
        value["status"]["containerStatuses"][0]["imageID"] = "docker-pullable://web:latest"
    elif mutation == "missing imageID":
        del value["status"]["containerStatuses"][0]["imageID"]
    return value


class RunningPodDigestTest(unittest.TestCase):
    def test_accepts_every_ready_replica_and_ignores_sidecars_and_terminating_pods(self) -> None:
        expected = expected_digests({"webImage": {"digest": WEB}, "apiImage": {"digest": API}})
        self.assertEqual(expected, {"web": WEB, "api": API})
        verify_pods(
            payloads([pod("web", WEB), pod("web", WEB), pod("web", API, terminating=True)], [pod("api", API)]),
            expected,
        )

    def test_rejects_missing_mixed_malformed_and_non_ready_pods(self) -> None:
        cases = (
            ("missing current web pod", payloads([], [pod("api", API)]), "no current web Pods"),
            ("web pod runs another selected digest", payloads([pod("web", API)], [pod("api", API)]), "runs"),
            ("web replicas disagree", payloads([pod("web", WEB), pod("web", API)], [pod("api", API)]), "runs"),
            ("web pod is not ready", payloads([pod("web", WEB, ready=False)], [pod("api", API)]), "not Running and Ready"),
        )
        for name, case, pattern in cases:
            with self.subTest(case=name), self.assertRaisesRegex(PodDigestError, pattern):
                verify_pods(case, {"web": WEB, "api": API})

        malformed_cases = (
            ("status is absent", "status", "status is malformed"),
            ("container statuses are absent", "containerStatuses", "containerStatuses are malformed"),
            ("business container is absent", "business", "business container is not Ready"),
            ("business image ID has no digest", "imageID", "no terminal sha256 digest"),
            ("business image ID is absent", "missing imageID", "must be a string"),
        )
        for name, mutation, pattern in malformed_cases:
            with self.subTest(case=name), self.assertRaisesRegex(PodDigestError, pattern):
                verify_pods(payloads([malformed_pod(mutation)], [pod("api", API)]), {"web": WEB, "api": API})

    def test_parses_only_terminal_digest(self) -> None:
        self.assertEqual(terminal_digest(f"containerd://repo@{WEB}"), WEB)
        for name, image_id, pattern in (
            ("digest is followed by a suffix", f"{WEB}:suffix", "no terminal sha256 digest"),
            ("image ID is not text", None, "must be a string"),
        ):
            with self.subTest(case=name), self.assertRaisesRegex(PodDigestError, pattern):
                terminal_digest(image_id)


if __name__ == "__main__":
    unittest.main()
