#!/usr/bin/env python3
"""Synchronize one GitHub issue with the public uptime monitor state."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable, Sequence


INCIDENT_TITLE = "Live Demo external monitor failed"
CommandRunner = Callable[[Sequence[str]], str]


def run_gh(arguments: Sequence[str]) -> str:
    result = subprocess.run(
        ["gh", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def find_open_incident(repository: str, runner: CommandRunner = run_gh) -> int | None:
    output = runner(
        [
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            "open",
            "--search",
            f'"{INCIDENT_TITLE}" in:title',
            "--json",
            "number,title",
            "--limit",
            "100",
        ]
    )
    issues = json.loads(output)
    matching_numbers = sorted(
        issue["number"] for issue in issues if issue.get("title") == INCIDENT_TITLE
    )
    return matching_numbers[0] if matching_numbers else None


def synchronize_incident(
    status: str,
    repository: str,
    run_url: str,
    runner: CommandRunner = run_gh,
) -> None:
    incident_number = find_open_incident(repository, runner)

    if status == "failure":
        if incident_number is None:
            body = (
                f"The public HTTPS or WebSocket check failed in {run_url}.\n\n"
                "This incident tracks public uptime only. Internal readiness is "
                "checked separately by deployment operations."
            )
            runner(
                [
                    "issue",
                    "create",
                    "--repo",
                    repository,
                    "--title",
                    INCIDENT_TITLE,
                    "--body",
                    body,
                ]
            )
            return

        runner(
            [
                "issue",
                "comment",
                str(incident_number),
                "--repo",
                repository,
                "--body",
                f"The public HTTPS or WebSocket check failed again in {run_url}.",
            ]
        )
        return

    if status == "success" and incident_number is not None:
        runner(
            [
                "issue",
                "close",
                str(incident_number),
                "--repo",
                repository,
                "--comment",
                (
                    "Public HTTPS and WebSocket checks recovered in "
                    f"{run_url}. Internal readiness remains a separate surface."
                ),
            ]
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", choices=("failure", "success"), required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-url", required=True)
    args = parser.parse_args()
    synchronize_incident(args.status, args.repository, args.run_url)


if __name__ == "__main__":
    main()
