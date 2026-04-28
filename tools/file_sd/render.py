#!/usr/bin/env python3
"""Render Prometheus file-SD YAML from an /etc/hosts-style file.

Input lines use normal hosts syntax:

    ADDRESS CANONICAL_NAME [ALIASES...] # key=value key=value ...

Plain comments are ignored. ``key=value`` pairs in comments are optional render
directives. ``probe=`` selects the output file, while other valid Prometheus
label names become file-SD labels unless they are renderer control keys such as
``target=``, ``scheme=``, ``path=``, or ``port=``.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from string import Template

GENERATED_BY = "tools/file_sd/render.py"
DEFAULT_HOSTS = Path("tools/file_sd/targets.example.hosts")
DEFAULT_TEMPLATE_DIR = Path("tools/file_sd/templates")
DEFAULT_OUT_DIR = Path("build/file_sd")
DEFAULT_TEMPLATE = "file_sd.yml.tmpl"

LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONTROL_KEYS = frozenset({"path", "port", "probe", "scheme", "target"})

RenderedFile = tuple[str, str]


class ConfigError(Exception):
    """Raised when the hosts input or template configuration is invalid."""


class Probe(StrEnum):
    """Supported probe groups mapped to Prometheus file-SD target files."""

    ICMP = "icmp"
    ICMP_IPV6 = "icmp_ipv6"
    HTTP_HEAD_200 = "http_head_200"
    HTTP_HEAD_200_IPV6 = "http_head_200_ipv6"
    HTTP_GET_BODY = "http_get_body"
    HTTP_GET_BODY_IPV6 = "http_get_body_ipv6"
    HTTPS_CERT = "https_cert"
    HTTPS_CERT_IPV6 = "https_cert_ipv6"
    TCP_CONNECT = "tcp_connect"
    TCP_CONNECT_IPV6 = "tcp_connect_ipv6"
    TCP_TLS = "tcp_tls"
    TCP_TLS_IPV6 = "tcp_tls_ipv6"
    DNS_UDP_A = "dns_udp_a"
    DNS_UDP_AAAA = "dns_udp_aaaa"


PROBE_FILES: Mapping[Probe, str] = {
    Probe.ICMP: "icmp_targets.yml",
    Probe.ICMP_IPV6: "icmp_ipv6_targets.yml",
    Probe.HTTP_HEAD_200: "http_targets.yml",
    Probe.HTTP_HEAD_200_IPV6: "http_ipv6_targets.yml",
    Probe.HTTP_GET_BODY: "http_body_targets.yml",
    Probe.HTTP_GET_BODY_IPV6: "http_body_ipv6_targets.yml",
    Probe.HTTPS_CERT: "https_targets.yml",
    Probe.HTTPS_CERT_IPV6: "https_ipv6_targets.yml",
    Probe.TCP_CONNECT: "tcp_targets.yml",
    Probe.TCP_CONNECT_IPV6: "tcp_ipv6_targets.yml",
    Probe.TCP_TLS: "tcp_tls_targets.yml",
    Probe.TCP_TLS_IPV6: "tcp_tls_ipv6_targets.yml",
    Probe.DNS_UDP_A: "dns_targets.yml",
    Probe.DNS_UDP_AAAA: "dns_aaaa_targets.yml",
}

PROBE_ALIASES: Mapping[str, Probe] = {
    "dns": Probe.DNS_UDP_A,
    "dns6": Probe.DNS_UDP_AAAA,
    "dns_udp_a": Probe.DNS_UDP_A,
    "dns_udp_aaaa": Probe.DNS_UDP_AAAA,
    "http": Probe.HTTP_HEAD_200,
    "http6": Probe.HTTP_HEAD_200_IPV6,
    "http_head_200": Probe.HTTP_HEAD_200,
    "http_head_200_ipv6": Probe.HTTP_HEAD_200_IPV6,
    "httping": Probe.HTTP_HEAD_200,
    "httping6": Probe.HTTP_HEAD_200_IPV6,
    "http_get_body": Probe.HTTP_GET_BODY,
    "http_get_body_ipv6": Probe.HTTP_GET_BODY_IPV6,
    "https": Probe.HTTPS_CERT,
    "https6": Probe.HTTPS_CERT_IPV6,
    "https_cert": Probe.HTTPS_CERT,
    "https_cert_ipv6": Probe.HTTPS_CERT_IPV6,
    "icmp": Probe.ICMP,
    "icmp6": Probe.ICMP_IPV6,
    "icmp_ipv6": Probe.ICMP_IPV6,
    "ping": Probe.ICMP,
    "ping6": Probe.ICMP_IPV6,
    "tcp": Probe.TCP_CONNECT,
    "tcp6": Probe.TCP_CONNECT_IPV6,
    "tcp_connect": Probe.TCP_CONNECT,
    "tcp_connect_ipv6": Probe.TCP_CONNECT_IPV6,
    "tcp_tls": Probe.TCP_TLS,
    "tcp_tls_ipv6": Probe.TCP_TLS_IPV6,
    "tcping": Probe.TCP_CONNECT,
    "tcping6": Probe.TCP_CONNECT_IPV6,
}


@dataclass(frozen=True, slots=True)
class RenderConfig:
    """Command-line configuration for one render run."""

    hosts: Path
    template_dir: Path
    out_dir: Path
    check: bool = False


@dataclass(frozen=True, slots=True)
class HostsRecord:
    """One parsed /etc/hosts-style line."""

    line_no: int
    address: str
    names: tuple[str, ...]
    attrs: dict[str, str]

    @property
    def canonical_name(self) -> str:
        """Return the first hostname, falling back to the address."""

        return self.names[0] if self.names else self.address


@dataclass(frozen=True, slots=True)
class TargetGroup:
    """One file-SD target entry with labels."""

    target: str
    labels: dict[str, str]


def yaml_quote(value: str) -> str:
    """Return a conservative double-quoted YAML scalar."""

    return json.dumps(value, ensure_ascii=True)


def parse_attrs(comment: str, line_no: int) -> dict[str, str]:
    """Parse key=value directives from a hosts-file comment."""

    attrs: dict[str, str] = {}
    try:
        tokens = shlex.split(comment, comments=False, posix=True)
    except ValueError as exc:
        raise ConfigError(f"line {line_no}: invalid comment directives: {exc}") from exc

    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if not key:
            raise ConfigError(f"line {line_no}: empty directive key")
        attrs[key] = value

    return attrs


def parse_hosts_line(line: str, line_no: int) -> HostsRecord | None:
    """Parse one hosts line, returning ``None`` for blanks and comments."""

    body, _, comment = line.partition("#")
    fields = body.split()
    if not fields:
        return None

    address, *names = fields
    return HostsRecord(
        line_no=line_no,
        address=address,
        names=tuple(names),
        attrs=parse_attrs(comment, line_no),
    )


def parse_hosts_file(path: Path) -> list[HostsRecord]:
    """Parse an /etc/hosts-style input file."""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ConfigError(f"{path}: {exc}") from exc

    records: list[HostsRecord] = []
    for line_no, line in enumerate(lines, start=1):
        record = parse_hosts_line(line, line_no)
        if record is not None:
            records.append(record)

    if not records:
        raise ConfigError(f"{path}: no hosts entries found")

    return records


def parse_probe(record: HostsRecord) -> Probe:
    """Resolve a record's probe directive."""

    raw_probe = record.attrs.get("probe", Probe.ICMP.value)
    try:
        return PROBE_ALIASES[raw_probe]
    except KeyError as exc:
        choices = ", ".join(sorted(PROBE_ALIASES))
        raise ConfigError(
            f"line {record.line_no}: unsupported probe {raw_probe!r}; "
            f"expected one of: {choices}"
        ) from exc


def parse_port(record: HostsRecord, default: str) -> str:
    """Return a validated TCP/UDP port string."""

    port = record.attrs.get("port", default)
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ConfigError(f"line {record.line_no}: invalid port {port!r}")
    return port


def normalize_path(record: HostsRecord) -> str:
    """Return an HTTP path that starts with ``/`` or an empty path."""

    path = record.attrs.get("path", "")
    if not path:
        return ""
    return path if path.startswith("/") else f"/{path}"


def format_host_port(host: str, port: str) -> str:
    """Return a host:port target, bracketing IPv6 literals when needed."""

    if ":" in host and not host.startswith("["):
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def format_url_host(host: str) -> str:
    """Return a URL host, bracketing IPv6 literals when needed."""

    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def target_for_probe(record: HostsRecord, probe: Probe) -> str:
    """Build the Blackbox target for a hosts record and probe type."""

    if target := record.attrs.get("target"):
        return target

    match probe:
        case Probe.ICMP | Probe.ICMP_IPV6:
            return record.address
        case (
            Probe.HTTP_HEAD_200
            | Probe.HTTP_HEAD_200_IPV6
            | Probe.HTTP_GET_BODY
            | Probe.HTTP_GET_BODY_IPV6
            | Probe.HTTPS_CERT
            | Probe.HTTPS_CERT_IPV6
        ):
            scheme = record.attrs.get("scheme", "https")
            path = normalize_path(record)
            return f"{scheme}://{format_url_host(record.canonical_name)}{path}"
        case (
            Probe.TCP_CONNECT
            | Probe.TCP_CONNECT_IPV6
            | Probe.TCP_TLS
            | Probe.TCP_TLS_IPV6
        ):
            return format_host_port(record.canonical_name, parse_port(record, "443"))
        case Probe.DNS_UDP_A:
            return format_host_port(record.address, parse_port(record, "53"))
        case Probe.DNS_UDP_AAAA:
            return format_host_port(record.address, parse_port(record, "53"))


def labels_for_record(record: HostsRecord, probe: Probe) -> dict[str, str]:
    """Build Prometheus labels for a rendered target."""

    labels = {
        "address": record.address,
        "group": record.attrs.get("group", "hosts"),
        "host": record.canonical_name,
        "probe": probe.value,
    }
    if aliases := record.names[1:]:
        labels["aliases"] = ",".join(aliases)
    if probe in {Probe.DNS_UDP_A, Probe.DNS_UDP_AAAA}:
        labels["dns_query"] = record.attrs.get("dns_query", record.canonical_name)

    for key, value in record.attrs.items():
        if key in CONTROL_KEYS:
            continue
        if not LABEL_RE.match(key):
            raise ConfigError(
                f"line {record.line_no}: invalid label name {key!r}; "
                "use Prometheus label syntax [A-Za-z_][A-Za-z0-9_]*"
            )
        labels[key] = value

    return labels


def render_targets(targets: Iterable[TargetGroup]) -> str:
    """Render a list of file-SD target groups."""

    blocks: list[str] = []
    for group in targets:
        labels = "\n".join(
            f"    {key}: {yaml_quote(value)}" for key, value in group.labels.items()
        )
        blocks.append(f"- targets:\n    - {yaml_quote(group.target)}\n  labels:\n{labels}")

    return "\n".join(blocks) if blocks else "[]"


def load_template(template_dir: Path, name: str = DEFAULT_TEMPLATE) -> Template:
    """Load a template from ``template_dir`` without allowing path traversal."""

    if "/" in name or "\\" in name or name in {".", ".."}:
        raise ConfigError(f"invalid template name {name!r}")

    path = template_dir / name
    try:
        return Template(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def render_hosts(config: RenderConfig) -> list[RenderedFile]:
    """Render all known file-SD files from hosts records."""

    grouped = {file_name: [] for file_name in PROBE_FILES.values()}
    for record in parse_hosts_file(config.hosts):
        probe = parse_probe(record)
        file_name = PROBE_FILES[probe]
        grouped[file_name].append(
            TargetGroup(
                target=target_for_probe(record, probe),
                labels=labels_for_record(record, probe),
            )
        )

    template = load_template(config.template_dir)
    rendered: list[RenderedFile] = []
    for file_name, targets in grouped.items():
        content = template.substitute(
            generated_by=GENERATED_BY,
            hosts=str(config.hosts),
            file=file_name,
            target_count=str(len(targets)),
            groups=render_targets(targets),
        )
        rendered.append((file_name, content if content.endswith("\n") else f"{content}\n"))

    return rendered


def write_outputs(rendered: Iterable[RenderedFile], out_dir: Path) -> None:
    """Write rendered files to ``out_dir``."""

    out_dir.mkdir(parents=True, exist_ok=True)
    for file_name, content in rendered:
        output_path = out_dir / file_name
        output_path.write_text(content, encoding="utf-8")
        print(f"Wrote {output_path}")


def repo_root() -> Path:
    """Return the repository root inferred from this script path."""

    return Path(__file__).resolve().parents[2]


def parse_args(argv: Sequence[str] | None = None) -> RenderConfig:
    """Parse CLI arguments into a typed render config."""

    root = repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hosts",
        type=Path,
        default=root / DEFAULT_HOSTS,
        help="/etc/hosts-style input path",
    )
    parser.add_argument(
        "--template-dir",
        type=Path,
        default=root / DEFAULT_TEMPLATE_DIR,
        help="template directory",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=root / DEFAULT_OUT_DIR,
        help="output directory",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate and render in memory without writing files",
    )
    namespace = parser.parse_args(argv)
    return RenderConfig(
        hosts=namespace.hosts,
        template_dir=namespace.template_dir,
        out_dir=namespace.out_dir,
        check=namespace.check,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line renderer."""

    config = parse_args(argv)
    try:
        rendered = render_hosts(config)
        if not config.check:
            write_outputs(rendered, config.out_dir)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
