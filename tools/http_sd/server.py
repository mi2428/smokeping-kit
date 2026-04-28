#!/usr/bin/env python3
"""Serve Prometheus HTTP service discovery target groups.

This is intentionally small and easy to edit. Replace ``discover_targets()``
with calls to your CMDB, cloud API, inventory file, service catalog, or any
other source that can produce Blackbox Exporter targets.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, TypedDict
from urllib.parse import unquote, urlparse

LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESERVED_TARGET_LABELS = frozenset({"module", "probe", "source"})

MODULE_PROBE_LABELS: Mapping[str, str] = {
    "dns_udp_a": "dns",
    "dns_udp_aaaa": "dns6",
    "http_get_body": "http_get_body",
    "http_get_body_ipv6": "http_get_body_ipv6",
    "http_head_200": "httping",
    "http_head_200_ipv6": "httping6",
    "https_cert": "https_cert",
    "https_cert_ipv6": "https_cert_ipv6",
    "icmp_ipv4": "icmp",
    "icmp_ipv6": "icmp6",
    "tcp_connect": "tcping",
    "tcp_connect_ipv6": "tcping6",
    "tcp_tls": "tcp_tls",
    "tcp_tls_ipv6": "tcp_tls_ipv6",
}


class ConfigError(Exception):
    """Raised when generated target groups are invalid."""


class TargetGroup(TypedDict):
    """Prometheus HTTP SD target group."""

    targets: list[str]
    labels: dict[str, str]


@dataclass(frozen=True, slots=True)
class BlackboxTarget:
    """One target to be probed by Blackbox Exporter."""

    target: str
    module: str
    labels: Mapping[str, str] = field(default_factory=dict)


def discover_targets() -> list[BlackboxTarget]:
    """Return Blackbox targets for Prometheus HTTP SD.

    This is the intended customization point.

    Replace this function with code that reads your inventory source and
    returns ``BlackboxTarget`` entries. Typical implementations read YAML/JSON,
    query cloud tags, call a CMDB, inspect service registries, or generate
    targets from DNS records.

    Contract:
    - ``target`` is the Blackbox target, such as ``https://example.com``.
    - ``module`` is one key from ``MODULE_PROBE_LABELS``.
    - ``labels`` are copied to Prometheus, except reserved labels validated by
      ``labels_for_target()``.

    Keep the default empty for template repositories: starting the stack should
    not immediately probe the public internet or fire alerts.
    """

    return []


def labels_for_target(target: BlackboxTarget) -> dict[str, str]:
    """Build and validate labels for one target group."""

    try:
        probe = MODULE_PROBE_LABELS[target.module]
    except KeyError as exc:
        choices = ", ".join(sorted(MODULE_PROBE_LABELS))
        raise ConfigError(
            f"unsupported module {target.module!r}; expected one of: {choices}"
        ) from exc

    labels = {
        "group": "http_sd",
        "module": target.module,
        "probe": probe,
        "source": "http_sd",
    }
    for key in target.labels:
        if key in RESERVED_TARGET_LABELS:
            choices = ", ".join(sorted(RESERVED_TARGET_LABELS))
            raise ConfigError(f"label {key!r} is reserved; reserved labels: {choices}")

    labels.update({key: str(value) for key, value in target.labels.items()})

    for key in labels:
        if not LABEL_RE.match(key):
            raise ConfigError(
                f"invalid label name {key!r}; "
                "use Prometheus label syntax [A-Za-z_][A-Za-z0-9_]*"
            )

    return labels


def target_groups(probe_filter: str | None = None) -> list[TargetGroup]:
    """Return HTTP SD target groups, optionally filtered by probe/module."""

    groups: list[TargetGroup] = []
    for target in discover_targets():
        labels = labels_for_target(target)
        if probe_filter and probe_filter not in {
            labels["module"],
            labels["probe"],
        }:
            continue

        groups.append(
            {
                "targets": [target.target],
                "labels": labels,
            }
        )

    return groups


def json_bytes(payload: Any) -> bytes:
    """Encode a JSON response."""

    return json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")


class HttpSdHandler(BaseHTTPRequestHandler):
    """HTTP handler for health checks and Prometheus HTTP SD."""

    server_version = "smokeping-kit-http-sd/0.1"

    def do_GET(self) -> None:
        """Handle HTTP GET requests."""

        path = unquote(urlparse(self.path).path)
        try:
            if path == "/healthz":
                self.write_json({"status": "ok"})
                return
            if path == "/sd":
                self.write_json(target_groups())
                return
            if path.startswith("/sd/"):
                self.write_json(target_groups(path.removeprefix("/sd/")))
                return

            self.write_json(
                {"error": "not found"},
                status=HTTPStatus.NOT_FOUND,
            )
        except ConfigError as exc:
            self.write_json(
                {"error": str(exc)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def write_json(
        self,
        payload: Any,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        """Write a JSON response."""

        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default=os.getenv("HTTP_SD_HOST", "127.0.0.1"),
        help="listen host",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("HTTP_SD_PORT", "8080")),
        help="listen port",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate discovery output without starting the server",
    )
    parser.add_argument(
        "--dump",
        action="store_true",
        help="print discovery output as JSON and exit",
    )
    return parser.parse_args(argv)


def check() -> int:
    """Validate discovery output."""

    groups = target_groups()
    json.dumps(groups)
    print(f"ok: {len(groups)} target groups")
    return 0


def run_server(host: str, port: int) -> int:
    """Run the HTTP SD server."""

    address = (host, port)
    with ThreadingHTTPServer(address, HttpSdHandler) as server:
        print(f"serving http_sd on {host}:{port}", flush=True)
        server.serve_forever()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line entry point."""

    args = parse_args(argv)
    try:
        if args.check:
            return check()
        if args.dump:
            print(json.dumps(target_groups(), ensure_ascii=True, indent=2))
            return 0
        return run_server(args.host, args.port)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
