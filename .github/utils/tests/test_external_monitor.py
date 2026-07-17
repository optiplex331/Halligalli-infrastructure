import base64
import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from external_monitor import check_https, check_websocket  # noqa: E402


class ExternalMonitorTest(unittest.TestCase):
    @patch("external_monitor.http.client.HTTPSConnection")
    def test_https_requires_status_200(self, connection_type: Mock) -> None:
        response = connection_type.return_value.getresponse.return_value
        response.status = 200
        check_https("https://play.halligalli.games")
        response.status = 503
        with self.assertRaisesRegex(RuntimeError, "503"):
            check_https("https://play.halligalli.games")

    @patch("external_monitor.os.urandom", return_value=b"a" * 16)
    @patch("external_monitor.http.client.HTTPSConnection")
    def test_websocket_requires_valid_upgrade(self, connection_type: Mock, _random: Mock) -> None:
        key = base64.b64encode(b"a" * 16).decode()
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        response = connection_type.return_value.getresponse.return_value
        response.status = 101
        response.getheader.return_value = accept
        check_websocket("https://play.halligalli.games", "/ws/v1/rooms/monitor")
        connection_type.return_value.putrequest.assert_called_with("GET", "/ws/v1/rooms/monitor", skip_host=True)
        response.status = 200
        with self.assertRaisesRegex(RuntimeError, "200"):
            check_websocket("https://play.halligalli.games", "/ws/v1/rooms/monitor")


if __name__ == "__main__":
    unittest.main()
