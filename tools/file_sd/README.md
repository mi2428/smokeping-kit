# File-SD Renderer

This optional helper generates Prometheus file service discovery YAML from an `/etc/hosts`-style file.

```console
$ cp tools/file_sd/hosts.example tools/file_sd/hosts
$ make render  # Write generated files to docker/prometheus/file_sd
$ make reload
```

Input shape:

```text
93.184.216.34                            example.com     # probe=httping   group=examples
93.184.216.34                            example.com     # probe=tcping    group=examples     port=443
127.0.0.11                               docker-dns      # probe=dns       group=docker       dns_query=example.com
2606:2800:220:1:248:1893:25c8:1946      example.com     # probe=httping6  group=examples-v6
2606:4700:4700::1111                     cloudflare-dns  # probe=dns6      group=dns-v6       dns_query=example.com
```

## Supported Probes

Use `target=...` to override the generated target.
Keep the generated labels aligned with the scrape jobs in `docker/prometheus/prometheus.yml` and the modules in `docker/blackbox/blackbox.yml`.

| Probe | Alias | Output file | What it checks |
| --- | --- | --- | --- |
| `icmp` | `ping` | `icmp_targets.yml` | ICMP echo reachability and RTT over IPv4. |
| `icmp6` | `ping6`, `icmp_ipv6` | `icmp_ipv6_targets.yml` | ICMP echo reachability and RTT over IPv6. |
| `httping` | `http`, `http_head_200` | `http_targets.yml` | HTTP HEAD returns status 200 over IPv4. |
| `httping6` | `http6`, `http_head_200_ipv6` | `http_ipv6_targets.yml` | HTTP HEAD returns status 200 over IPv6. |
| `http_get_body` | - | `http_body_targets.yml` | HTTP GET returns 200 and matches the body regexp. |
| `http_get_body_ipv6` | - | `http_body_ipv6_targets.yml` | HTTP GET returns 200 and matches the body regexp over IPv6. |
| `https_cert` | `https` | `https_targets.yml` | HTTPS reachability and TLS certificate metrics over IPv4. |
| `https_cert_ipv6` | `https6` | `https_ipv6_targets.yml` | HTTPS reachability and TLS certificate metrics over IPv6. |
| `tcping` | `tcp`, `tcp_connect` | `tcp_targets.yml` | Plain TCP connect reachability and duration over IPv4. |
| `tcping6` | `tcp6`, `tcp_connect_ipv6` | `tcp_ipv6_targets.yml` | Plain TCP connect reachability and duration over IPv6. |
| `tcp_tls` | - | `tcp_tls_targets.yml` | TCP connect plus TLS handshake over IPv4. |
| `tcp_tls_ipv6` | - | `tcp_tls_ipv6_targets.yml` | TCP connect plus TLS handshake over IPv6. |
| `dns` | `dns_udp_a` | `dns_targets.yml` | DNS UDP A query against the target resolver. |
| `dns6` | `dns_udp_aaaa` | `dns_aaaa_targets.yml` | DNS UDP AAAA query against the target resolver over IPv6. |
