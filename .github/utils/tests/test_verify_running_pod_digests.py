import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_running_pod_digests import PodDigestError, expected_digests, terminal_digest, verify_pods  # noqa: E402


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


class RunningPodDigestTest(unittest.TestCase):
    def test_accepts_every_ready_replica_and_ignores_sidecars_and_terminating_pods(self) -> None:
        verify_pods(payloads([pod("web", WEB), pod("web", WEB), pod("web", API, terminating=True)], [pod("api", API)]), {"web": WEB, "api": API})

    def test_rejects_missing_mixed_malformed_and_non_ready_pods(self) -> None:
        cases = [
            payloads([], [pod("api", API)]),
            payloads([pod("web", API)], [pod("api", API)]),
            payloads([pod("web", WEB), pod("web", API)], [pod("api", API)]),
            payloads([pod("web", WEB, ready=False)], [pod("api", API)]),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(PodDigestError):
                verify_pods(case, {"web": WEB, "api": API})
        malformed = pod("web", WEB); malformed["status"]["containerStatuses"][0]["imageID"] = "docker-pullable://web:latest"
        with self.assertRaises(PodDigestError):
            verify_pods(payloads([malformed], [pod("api", API)]), {"web": WEB, "api": API})
        for mutation in ("status", "containerStatuses", "business", "imageID"):
            missing = pod("web", WEB)
            if mutation == "status":
                del missing["status"]
            elif mutation == "containerStatuses":
                del missing["status"]["containerStatuses"]
            elif mutation == "business":
                missing["status"]["containerStatuses"][0]["name"] = "other"
            else:
                del missing["status"]["containerStatuses"][0]["imageID"]
            with self.subTest(mutation=mutation), self.assertRaises(PodDigestError):
                verify_pods(payloads([missing], [pod("api", API)]), {"web": WEB, "api": API})

    def test_parses_values_and_only_terminal_digest(self) -> None:
        self.assertEqual(expected_digests({"webImage": {"digest": WEB}, "apiImage": {"digest": API}}), {"web": WEB, "api": API})
        self.assertEqual(terminal_digest(f"containerd://repo@{WEB}"), WEB)
        with self.assertRaises(PodDigestError):
            terminal_digest(f"{WEB}:suffix")


if __name__ == "__main__":
    unittest.main()
