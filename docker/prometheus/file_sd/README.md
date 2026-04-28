# File Service Discovery Targets

Each file in this directory is consumed by a matching `blackbox_*` scrape job in
`docker/prometheus/prometheus.yml`.

Target formats:

- `icmp_targets.yml`: host or IP.
- `icmp_ipv6_targets.yml`: IPv6 host or IP.
- `http_targets.yml`: URL with scheme, checked with HTTP HEAD and status 200.
- `http_ipv6_targets.yml`: URL with scheme, checked with HTTP HEAD over IPv6.
- `http_body_targets.yml`: URL with scheme, checked with HTTP GET and module body regexp.
- `http_body_ipv6_targets.yml`: URL with scheme, checked with HTTP GET body regexp over IPv6.
- `https_targets.yml`: HTTPS URL, checked for reachability and TLS certificate metrics.
- `https_ipv6_targets.yml`: HTTPS URL, checked for reachability and TLS certificate metrics over IPv6.
- `tcp_targets.yml`: `host:port`.
- `tcp_ipv6_targets.yml`: `host:port`, checked with IPv6 TCP connect.
- `tcp_tls_targets.yml`: `host:port`, checked with a TLS handshake.
- `tcp_tls_ipv6_targets.yml`: `host:port`, checked with an IPv6 TLS handshake.
- `dns_targets.yml`: DNS resolver as `host:port`.
- `dns_aaaa_targets.yml`: IPv6-capable DNS resolver as `host:port` or `[IPv6]:port`.

Prometheus refreshes these files every 30 seconds.

Labels are copied to Prometheus series and alerts. Common useful labels:

- `group`: site, team, region, or product grouping.
- `service`: human service name, for example `api`, `cdn`, `dns`.
- `env`: `prod`, `staging`, `dev`.
- `owner`: team or Slack channel name.

Alertmanager can route on any of these labels after you add them to targets.
