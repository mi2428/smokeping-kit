# File Service Discovery Targets

Each file in this directory is consumed by a matching `blackbox_*` scrape job in
`docker/prometheus/prometheus.yml`.

Target formats:

- `icmp_targets.yml`: host or IP.
- `http_targets.yml`: URL with scheme, checked with HTTP HEAD and status 200.
- `http_body_targets.yml`: URL with scheme, checked with HTTP GET and module body regexp.
- `https_targets.yml`: HTTPS URL, checked for reachability and TLS certificate metrics.
- `tcp_targets.yml`: `host:port`.
- `tcp_tls_targets.yml`: `host:port`, checked with a TLS handshake.
- `dns_targets.yml`: DNS resolver as `host:port`.

Prometheus refreshes these files every 30 seconds.

Labels are copied to Prometheus series and alerts. Common useful labels:

- `group`: site, team, region, or product grouping.
- `service`: human service name, for example `api`, `cdn`, `dns`.
- `env`: `prod`, `staging`, `dev`.
- `owner`: team or Slack channel name.

Alertmanager can route on any of these labels after you add them to targets.
