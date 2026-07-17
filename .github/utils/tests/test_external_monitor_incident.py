import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from external_monitor_incident import (  # noqa: E402
    INCIDENT_TITLE,
    find_open_incident,
    synchronize_incident,
)


REPOSITORY = "optiplex331/Halligalli-infrastructure"
RUN_URL = "https://github.com/example/repository/actions/runs/123"


class ExternalMonitorIncidentTest(unittest.TestCase):
    def test_find_open_incident_requires_exact_title(self) -> None:
        runner = Mock(
            return_value=json.dumps(
                [
                    {"number": 9, "title": f"{INCIDENT_TITLE} again"},
                    {"number": 7, "title": INCIDENT_TITLE},
                ]
            )
        )

        self.assertEqual(7, find_open_incident(REPOSITORY, runner))

    def test_failure_creates_incident_when_none_is_open(self) -> None:
        runner = Mock(side_effect=["[]", ""])

        synchronize_incident("failure", REPOSITORY, RUN_URL, runner)

        create_arguments = runner.call_args_list[1].args[0]
        self.assertEqual(["issue", "create"], create_arguments[:2])
        self.assertIn(INCIDENT_TITLE, create_arguments)
        self.assertIn(RUN_URL, create_arguments[-1])
        self.assertIn("Internal readiness", create_arguments[-1])

    def test_repeated_failure_updates_open_incident(self) -> None:
        open_issue = json.dumps([{"number": 42, "title": INCIDENT_TITLE}])
        runner = Mock(side_effect=[open_issue, ""])

        synchronize_incident("failure", REPOSITORY, RUN_URL, runner)

        self.assertEqual(
            ["issue", "comment", "42"],
            runner.call_args_list[1].args[0][:3],
        )
        self.assertIn(RUN_URL, runner.call_args_list[1].args[0][-1])

    def test_recovery_records_success_and_closes_open_incident(self) -> None:
        open_issue = json.dumps([{"number": 42, "title": INCIDENT_TITLE}])
        runner = Mock(side_effect=[open_issue, ""])

        synchronize_incident("success", REPOSITORY, RUN_URL, runner)

        self.assertEqual(
            ["issue", "close", "42"],
            runner.call_args_list[1].args[0][:3],
        )
        self.assertIn(RUN_URL, runner.call_args_list[1].args[0][-1])

    def test_success_without_open_incident_does_not_write(self) -> None:
        runner = Mock(return_value="[]")

        synchronize_incident("success", REPOSITORY, RUN_URL, runner)

        self.assertEqual(1, runner.call_count)
        self.assertEqual("issue", runner.call_args.args[0][0])
        self.assertEqual("list", runner.call_args.args[0][1])


if __name__ == "__main__":
    unittest.main()
