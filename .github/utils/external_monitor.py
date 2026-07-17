#!/usr/bin/env python3
"""Dependency-free public HTTPS and WebSocket availability checks."""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import os
import ssl
from urllib.parse import urlparse


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default="https://play.halligalli.games")
    parser.add_argument("--websocket-path", default="/ws/v1/rooms/monitor")
    args = parser.parse_args()
    check_https(args.origin)
    check_websocket(args.origin, args.websocket_path)


if __name__ == "__main__":
    main()
