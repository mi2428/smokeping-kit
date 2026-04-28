#!/usr/bin/env python3
"""Unit tests for the file-SD renderer."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render  # noqa: E402


class ParseTest(unittest.TestCase):
    """Tests for /etc/hosts-style parsing."""

    def test_parse_attrs_reads_key_value_tokens(self) -> None:
        attrs = render.parse_attrs(
            'probe=httping group=examples body_regexp="Example Domain" ignored',
            line_no=7,
        )

        self.assertEqual(
            attrs,
            {
                "body_regexp": "Example Domain",
                "group": "examples",
                "probe": "httping",
            },
        )

    def test_parse_attrs_rejects_invalid_shell_syntax(self) -> None:
        with self.assertRaisesRegex(render.ConfigError, "invalid comment directives"):
            render.parse_attrs('probe="unterminated', line_no=3)

    def test_parse_attrs_rejects_empty_key(self) -> None:
        with self.assertRaisesRegex(render.ConfigError, "empty directive key"):
            render.parse_attrs("=value", line_no=3)

    def test_parse_hosts_line_ignores_blank_and_comment_lines(self) -> None:
        self.assertIsNone(render.parse_hosts_line("", line_no=1))
        self.assertIsNone(render.parse_hosts_line("# comment", line_no=2))

    def test_parse_hosts_line_reads_address_names_and_attrs(self) -> None:
        record = render.parse_hosts_line(
            "93.184.216.34 example.com www # probe=httping group=examples",
            line_no=12,
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.line_no, 12)
        self.assertEqual(record.address, "93.184.216.34")
        self.assertEqual(record.names, ("example.com", "www"))
        self.assertEqual(record.attrs["probe"], "httping")

    def test_parse_hosts_file_rejects_empty_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hosts"
            path.write_text("# only comments\n\n", encoding="utf-8")

            with self.assertRaisesRegex(render.ConfigError, "no hosts entries found"):
                render.parse_hosts_file(path)


class TargetTest(unittest.TestCase):
    """Tests for probe resolution, target building, and labels."""

    def record(
        self,
        address: str = "93.184.216.34",
        names: tuple[str, ...] = ("example.com",),
        attrs: dict[str, str] | None = None,
    ) -> render.HostsRecord:
        """Build a HostsRecord for tests."""

        return render.HostsRecord(
            line_no=1,
            address=address,
            names=names,
            attrs=attrs or {},
        )

    def test_parse_probe_defaults_to_icmp(self) -> None:
        self.assertIs(render.parse_probe(self.record()), render.Probe.ICMP)

    def test_parse_probe_accepts_aliases(self) -> None:
        cases = {
            "dns6": render.Probe.DNS_UDP_AAAA,
            "httping6": render.Probe.HTTP_HEAD_200_IPV6,
            "ping": render.Probe.ICMP,
            "tcping": render.Probe.TCP_CONNECT,
        }
        for alias, expected in cases.items():
            with self.subTest(alias=alias):
                self.assertIs(
                    render.parse_probe(self.record(attrs={"probe": alias})),
                    expected,
                )

    def test_parse_probe_rejects_unknown_probe(self) -> None:
        with self.assertRaisesRegex(render.ConfigError, "unsupported probe"):
            render.parse_probe(self.record(attrs={"probe": "not_a_probe"}))

    def test_parse_port_validates_range(self) -> None:
        self.assertEqual(render.parse_port(self.record(attrs={"port": "8443"}), "443"), "8443")

        for port in ("0", "65536", "abc", "-1"):
            with self.subTest(port=port):
                with self.assertRaisesRegex(render.ConfigError, "invalid port"):
                    render.parse_port(self.record(attrs={"port": port}), "443")

    def test_normalize_path_adds_leading_slash(self) -> None:
        self.assertEqual(render.normalize_path(self.record(attrs={"path": "healthz"})), "/healthz")
        self.assertEqual(render.normalize_path(self.record(attrs={"path": "/ready"})), "/ready")
        self.assertEqual(render.normalize_path(self.record()), "")

    def test_target_for_probe_uses_explicit_target_override(self) -> None:
        record = self.record(attrs={"target": "https://override.example/healthz"})

        self.assertEqual(
            render.target_for_probe(record, render.Probe.HTTP_HEAD_200),
            "https://override.example/healthz",
        )

    def test_target_for_probe_builds_http_url(self) -> None:
        record = self.record(attrs={"scheme": "http", "path": "status"})

        self.assertEqual(
            render.target_for_probe(record, render.Probe.HTTP_HEAD_200),
            "http://example.com/status",
        )

    def test_target_for_probe_brackets_ipv6_http_literal(self) -> None:
        record = self.record(
            address="2606:4700:4700::1111",
            names=(),
            attrs={"path": "healthz"},
        )

        self.assertEqual(
            render.target_for_probe(record, render.Probe.HTTP_HEAD_200_IPV6),
            "https://[2606:4700:4700::1111]/healthz",
        )

    def test_target_for_probe_brackets_ipv6_dns_and_tcp_literals(self) -> None:
        record = self.record(
            address="2606:4700:4700::1111",
            names=(),
            attrs={"port": "53"},
        )

        self.assertEqual(
            render.target_for_probe(record, render.Probe.DNS_UDP_AAAA),
            "[2606:4700:4700::1111]:53",
        )
        self.assertEqual(
            render.target_for_probe(record, render.Probe.TCP_CONNECT_IPV6),
            "[2606:4700:4700::1111]:53",
        )

    def test_labels_for_record_includes_aliases_and_dns_query(self) -> None:
        record = self.record(
            names=("resolver.example", "resolver"),
            attrs={
                "dns_query": "example.com",
                "group": "dns",
                "probe": "dns",
                "service": "resolver",
            },
        )

        self.assertEqual(
            render.labels_for_record(record, render.Probe.DNS_UDP_A),
            {
                "address": "93.184.216.34",
                "aliases": "resolver",
                "dns_query": "example.com",
                "group": "dns",
                "host": "resolver.example",
                "probe": "dns_udp_a",
                "service": "resolver",
            },
        )

    def test_labels_for_record_ignores_control_keys(self) -> None:
        labels = render.labels_for_record(
            self.record(
                attrs={
                    "path": "healthz",
                    "port": "443",
                    "scheme": "http",
                    "target": "http://override",
                }
            ),
            render.Probe.HTTP_HEAD_200,
        )

        for key in ("path", "port", "scheme", "target"):
            self.assertNotIn(key, labels)

    def test_labels_for_record_rejects_invalid_label_name(self) -> None:
        with self.assertRaisesRegex(render.ConfigError, "invalid label name"):
            render.labels_for_record(
                self.record(attrs={"bad-label": "value"}),
                render.Probe.ICMP,
            )


class RenderTest(unittest.TestCase):
    """Tests for YAML rendering and file output."""

    def test_yaml_quote_uses_json_style_quotes(self) -> None:
        self.assertEqual(render.yaml_quote("line\nquote\""), '"line\\nquote\\""')

    def test_render_targets_returns_empty_list_for_no_targets(self) -> None:
        self.assertEqual(render.render_targets([]), "[]")

    def test_render_targets_outputs_targets_and_labels(self) -> None:
        text = render.render_targets(
            [
                render.TargetGroup(
                    target="https://example.com",
                    labels={"group": "examples", "probe": "http_head_200"},
                )
            ]
        )

        self.assertIn('- "https://example.com"', text)
        self.assertIn('    group: "examples"', text)
        self.assertIn('    probe: "http_head_200"', text)

    def test_load_template_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(render.ConfigError, "invalid template name"):
                render.load_template(Path(tmp), "../file_sd.yml.tmpl")

    def test_render_hosts_outputs_all_known_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hosts = root / "hosts"
            template_dir = root / "templates"
            template_dir.mkdir()
            hosts.write_text(
                "\n".join(
                    [
                        "93.184.216.34 example.com # probe=httping group=examples",
                        "2606:4700:4700::1111 cloudflare-dns # probe=dns6 dns_query=example.com",
                    ]
                ),
                encoding="utf-8",
            )
            (template_dir / render.DEFAULT_TEMPLATE).write_text(
                "# ${file} ${target_count}\n${groups}\n",
                encoding="utf-8",
            )

            rendered = dict(
                render.render_hosts(
                    render.RenderConfig(
                        hosts=hosts,
                        template_dir=template_dir,
                        out_dir=root / "out",
                    )
                )
            )

        self.assertEqual(set(rendered), set(render.PROBE_FILES.values()))
        self.assertIn('    - "https://example.com"', rendered["http_targets.yml"])
        self.assertIn(
            '    - "[2606:4700:4700::1111]:53"',
            rendered["dns_aaaa_targets.yml"],
        )
        self.assertTrue(rendered["icmp_targets.yml"].endswith("[]\n"))

    def test_write_outputs_writes_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            output = io.StringIO()
            with redirect_stdout(output):
                render.write_outputs([("one.yml", "content\n")], out_dir)

            self.assertEqual((out_dir / "one.yml").read_text(encoding="utf-8"), "content\n")
            self.assertIn("Wrote", output.getvalue())

    def test_main_check_does_not_write_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hosts = root / "hosts"
            template_dir = root / "templates"
            out_dir = root / "out"
            template_dir.mkdir()
            hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
            (template_dir / render.DEFAULT_TEMPLATE).write_text("${groups}\n", encoding="utf-8")

            exit_code = render.main(
                [
                    "--hosts",
                    str(hosts),
                    "--template-dir",
                    str(template_dir),
                    "--out-dir",
                    str(out_dir),
                    "--check",
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertFalse(out_dir.exists())

    def test_main_returns_zero_for_missing_hosts(self) -> None:
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(output):
            exit_code = render.main(
                [
                    "--hosts",
                    str(Path(tmp) / "missing"),
                    "--template-dir",
                    tmp,
                    "--check",
                ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("No hosts file found; nothing to render.", output.getvalue())

    def test_main_returns_zero_for_empty_hosts(self) -> None:
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(output):
            root = Path(tmp)
            hosts = root / "hosts"
            hosts.write_text("# no targets\n", encoding="utf-8")
            exit_code = render.main(
                [
                    "--hosts",
                    str(hosts),
                    "--template-dir",
                    tmp,
                    "--check",
                ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("No hosts entries found; nothing to render.", output.getvalue())


if __name__ == "__main__":
    unittest.main()
