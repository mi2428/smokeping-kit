# HTTP-SD Server

This helper is a small Prometheus HTTP service discovery app for Blackbox Exporter targets.

## Custom Discovery

Implement your own discovery by editing `discover_targets()` in `server.py`.

```python
def discover_targets() -> list[BlackboxTarget]:
    return [
        BlackboxTarget(
            # Blackbox probe target, for example `https://example.com`, `example.com:443`, or `1.1.1.1:53`.
            target="https://example.com",
            # Blackbox module name, for example `icmp_ipv4`, `http_head_200`, `tcp_connect`, or `dns_udp_aaaa`.
            module="http_head_200",
            # Prometheus labels copied onto the discovered series.
            labels={"group": "websites", "service": "homepage"},
        ),
    ]
```

The app validates module names and Prometheus label names before returning data.
`module`, `probe`, and `source` are reserved labels because the Prometheus scrape job uses `module` to set `__param_module`.

Validate locally:

```console
$ uv run python tools/http_sd/server.py --check
$ uv run python tools/http_sd/server.py --dump
$ uv run python -m unittest tools/http_sd/server_test.py
```
