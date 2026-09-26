#!/usr/bin/env python3
"""Dependency-free public HTTPS, WebSocket, and release identity checks."""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
import ssl
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

DESIRED_STATE_PATH = Path(__file__).resolve().parents[2] / "targets" / "container-apps" / "terraform" / "desired-state.json"
MANIFEST_URL = "https://github.com/optiplex331/Halligalli-BossYang/releases/download/v{version}/paired-release-manifest.json"


class ReleaseIdentityError(RuntimeError):
    """Raised when the running release cannot be matched to the desired state."""


def check_https(origin: str) -> None:
    parsed = urlparse(origin)
    connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=10, context=ssl.create_default_context())
    connection.request("GET", parsed.path or "/")
    response = connection.getresponse()
    response.read()
    if response.status != 200:
        raise RuntimeError(f"HTTPS returned {response.status}")


def check_websocket(origin: str, path: str) -> None:
    parsed = urlparse(origin)
    key = base64.b64encode(os.urandom(16)).decode()
    connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=10, context=ssl.create_default_context())
    connection.putrequest("GET", path, skip_host=True)
    connection.putheader("Host", parsed.hostname or "")
    connection.putheader("Upgrade", "websocket")
    connection.putheader("Connection", "Upgrade")
    connection.putheader("Sec-WebSocket-Key", key)
    connection.putheader("Sec-WebSocket-Version", "13")
    connection.endheaders()
    response = connection.getresponse()
    expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
    if response.status != 101 or response.getheader("Sec-WebSocket-Accept") != expected:
        raise RuntimeError(f"WebSocket handshake returned {response.status}")


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "Cache-Control": "no-cache", "User-Agent": "halligalli-live-demo-monitor"})
    with urllib.request.urlopen(request, timeout=10, context=ssl.create_default_context()) as response:
        return json.loads(response.read().decode("utf-8"))


def verify_release_identity(identity: Any, manifest: Any, desired_state: Any) -> None:
    """Match the running Web identity, via its Paired Release Manifest, to the desired Web/API digests."""
    if not isinstance(identity, dict) or not isinstance(identity.get("version"), str) or not isinstance(identity.get("commit"), str):
        raise ReleaseIdentityError("running release identity must contain string version and commit values")
    try:
        manifest_identity = manifest["runtimeIdentity"]
        released = {role: manifest["images"][role]["digest"] for role in ("web", "api")}
        desired = {"web": desired_state["webImage"]["digest"], "api": desired_state["apiImage"]["digest"]}
    except (KeyError, TypeError):
        raise ReleaseIdentityError("Paired Release Manifest or desired state is missing release identity fields") from None
    running = {"version": identity["version"], "commit": identity["commit"]}
    if manifest.get("releaseTag") != f"v{running['version']}" or manifest_identity != running:
        raise ReleaseIdentityError(f"Paired Release Manifest does not describe running release {running}")
    for role in ("web", "api"):
        if released[role] != desired[role]:
            raise ReleaseIdentityError(
                f"running release v{running['version']} {role} digest {released[role]} differs from desired state {desired[role]}"
            )


def check_release_identity(
    origin: str,
    desired_state_path: Path = DESIRED_STATE_PATH,
    fetch: Callable[[str], Any] = fetch_json,
) -> None:
    desired_state = json.loads(desired_state_path.read_text(encoding="utf-8"))
    try:
        identity = fetch(f"{origin.rstrip('/')}/internal/identity")
    except (OSError, ValueError) as error:
        raise ReleaseIdentityError(f"cannot read running release identity: {error}") from error
    version = identity.get("version") if isinstance(identity, dict) else None
    if not isinstance(version, str):
        raise ReleaseIdentityError("running release identity must contain a string version")
    try:
        manifest = fetch(MANIFEST_URL.format(version=version))
    except (OSError, ValueError) as error:
        raise ReleaseIdentityError(f"cannot read Paired Release Manifest for v{version}: {error}") from error
    verify_release_identity(identity, manifest, desired_state)


def run_report(checks: list[tuple[str, Callable[[], None]]]) -> list[tuple[str, str | None]]:
    """Run every check without stopping at the first failure; return (name, error or None)."""
    results: list[tuple[str, str | None]] = []
    for name, check in checks:
        try:
            check()
        except Exception as error:  # noqa: BLE001 - report-only mode records every failure
            results.append((name, f"{type(error).__name__}: {error}"))
        else:
            results.append((name, None))
    return results


def render_report(origin: str, results: list[tuple[str, str | None]]) -> str:
    lines = [f"## Live Demo report for {origin}", "", "| Check | Result |", "|---|---|"]
    for name, error in results:
        result = "pass" if error is None else f"FAIL: {error}".replace("|", "\\|")
        lines.append(f"| {name} | {result} |")
    lines += ["", "Report-only: failures do not fail this run. Drift is expected between a merged promotion and its approved apply."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default="https://play.halligalli.games")
    parser.add_argument("--websocket-path", default="/ws/v1/rooms/monitor")
    parser.add_argument("--desired-state", type=Path, default=DESIRED_STATE_PATH)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="run every check, write results to $GITHUB_STEP_SUMMARY (or stdout), and exit 0; the default fails on the first error",
    )
    args = parser.parse_args()
    checks: list[tuple[str, Callable[[], None]]] = [
        ("HTTPS", lambda: check_https(args.origin)),
        ("WebSocket", lambda: check_websocket(args.origin, args.websocket_path)),
        ("Release identity and desired-state drift", lambda: check_release_identity(args.origin, args.desired_state)),
    ]
    if not args.report_only:
        for _, check in checks:
            check()
        return
    report = render_report(args.origin, run_report(checks))
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write(report)
    print(report, end="")


if __name__ == "__main__":
    main()
