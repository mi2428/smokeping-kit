#!/usr/bin/env python3
"""Unit tests for the HTTP service discovery helper."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402


def discovered_targets() -> list[server.BlackboxTarget]:
    """Return deterministic targets for tests."""

    return [
        server.BlackboxTarget(
            target="https://example.com",
            module="http_head_200",
            labels={
                "group": "websites",
                "service": "homepage",
            },
        ),
        server.BlackboxTarget(
            target="example.com:443",
            module="tcp_connect",
            labels={
                "group": "websites",
                "service": "homepage",
            },
        ),
        server.BlackboxTarget(
            target="1.1.1.1:53",
            module="dns_udp_a",
            labels={
                "dns_query": "example.com",
                "group": "dns",
                "service": "resolver",
            },
        ),
    ]


class DiscoveryTest(unittest.TestCase):
    """Tests for discovery output and validation."""

    def test_default_discovery_is_empty(self) -> None:
        self.assertEqual(server.discover_targets(), [])
        self.assertEqual(server.target_groups(), [])

    def test_custom_discovery_returns_valid_target_groups(self) -> None:
        with patch("server.discover_targets", discovered_targets):
            groups = server.target_groups()

        self.assertEqual(len(groups), 3)
        self.assertEqual(groups[0]["targets"], ["https://example.com"])
        self.assertEqual(groups[0]["labels"]["module"], "http_head_200")
        self.assertEqual(groups[0]["labels"]["probe"], "httping")
        self.assertEqual(groups[0]["labels"]["source"], "http_sd")

    def test_target_groups_can_filter_by_probe_or_module(self) -> None:
        with patch("server.discover_targets", discovered_targets):
            by_probe = server.target_groups("httping")
            by_module = server.target_groups("http_head_200")

        self.assertEqual(by_probe, by_module)
        self.assertEqual(by_probe[0]["targets"], ["https://example.com"])

    def test_labels_for_target_maps_module_to_probe(self) -> None:
        labels = server.labels_for_target(
            server.BlackboxTarget(
                target="example.com:443",
                module="tcp_connect",
                labels={"group": "edge", "priority": "1"},
            )
        )

        self.assertEqual(
            labels,
            {
                "group": "edge",
                "module": "tcp_connect",
                "priority": "1",
                "probe": "tcping",
                "source": "http_sd",
            },
        )

    def test_labels_for_target_rejects_unknown_module(self) -> None:
        with self.assertRaisesRegex(server.ConfigError, "unsupported module"):
            server.labels_for_target(
                server.BlackboxTarget(target="example.com", module="unknown")
            )

    def test_labels_for_target_rejects_invalid_label_name(self) -> None:
        with self.assertRaisesRegex(server.ConfigError, "invalid label name"):
            server.labels_for_target(
                server.BlackboxTarget(
                    target="example.com",
                    module="icmp_ipv4",
                    labels={"bad-label": "value"},
                )
            )

    def test_labels_for_target_rejects_reserved_label_names(self) -> None:
        for key in ("module", "probe", "source"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(server.ConfigError, "reserved"):
                    server.labels_for_target(
                        server.BlackboxTarget(
                            target="example.com",
                            module="icmp_ipv4",
                            labels={key: "override"},
                        )
                    )

    def test_json_bytes_returns_stable_json_bytes(self) -> None:
        self.assertEqual(server.json_bytes({"b": 1, "a": 2}), b'{"a": 2, "b": 1}')

    def test_check_validates_default_discovery(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = server.check()

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue().strip(), "ok: 0 target groups")

    def test_dump_output_is_valid_json_shape(self) -> None:
        with patch("server.discover_targets", discovered_targets):
            payload = json.loads(server.json_bytes(server.target_groups()))

        self.assertEqual(payload[0]["labels"]["module"], "http_head_200")


if __name__ == "__main__":
    unittest.main()
