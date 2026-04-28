# Smokeping Kit

Smokeping Kit builds network smoke-test monitoring with Docker Compose — Prometheus, Blackbox Exporter, Pushgateway, Alertmanager, and Grafana with ready-to-use probes, recording/alert rules, and dashboards.

[![](https://github.com/mi2428/smokeping-kit/blob/main/screenshot.png?raw=true)](https://github.com/mi2428/smokeping-kit/blob/main/screenshot.png)

## Getting Started

Create a repository from this template. Use `--public` for a public repository.
You need Docker with Compose v2, `make`, and `uv` to run this kit.

```console
$ gh auth login
$ gh repo create YOUR_ORG/YOUR_REPO --template mi2428/smokeping-kit --private --clone
```

After setting up the repository, copy the local files and edit what you need.

- Add or remove generated probe targets: `tools/file_sd/hosts`
- Edit Prometheus file-SD YAML directly: [`docker/prometheus/file_sd/*.yml`](docker/prometheus/file_sd/)
- Change Prometheus scrape jobs or wire a new Blackbox module: [`docker/prometheus/prometheus.yml`](docker/prometheus/prometheus.yml)
- Change probe behavior such as ICMP, HTTP, TCP, TLS, or DNS modules: [`docker/blackbox/blackbox.yml`](docker/blackbox/blackbox.yml)
- Change recording rules used by dashboards and alerts: [`docker/prometheus/rules/recording.yml`](docker/prometheus/rules/recording.yml)
- Change alert expressions, thresholds, labels, or annotations: [`docker/prometheus/rules/alerts.yml`](docker/prometheus/rules/alerts.yml)
- Route alerts to Slack, webhook, email, or another receiver: [`docker/alertmanager/alertmanager.yml`](docker/alertmanager/alertmanager.yml)

Run `make` to see the available commands and URLs.
The default setup publishes a single local entry point through Caddy.

```console
$ cp .env.example .env
$ cp tools/file_sd/hosts.example tools/file_sd/hosts
$ make

Stack
  up          Start the stack. Set DIRECT=1 to publish component ports directly
  down        Stop and remove the stack. Set DIRECT=1 for direct port mode
  restart     Restart running services
  pull        Pull latest service images
  ps          Show service status. Set DIRECT=1 for direct port mode
  logs        Follow logs. Set DIRECT=1 for direct port mode

Operations
  validate    Validate Compose, Caddy, Blackbox, Prometheus, and Alertmanager config
  check       Alias for validate
  render      Render file-SD target YAML from FILE_SD_HOSTS
  reload      Reload Prometheus, auto-detecting Caddy when available
  clean       Stop the stack and remove volumes. Set DIRECT=1 for direct port mode

Help
  help        Show this help message

Caddy URLs:
  Grafana                    http://localhost:9000/grafana/
  Prometheus                 http://localhost:9000/prometheus/
  Alertmanager               http://localhost:9000/alertmanager/
  Blackbox Exporter          http://localhost:9000/blackbox/
  Pushgateway                http://localhost:9000/pushgateway/
  HTTP-SD                    http://localhost:9000/http-sd/

Direct URLs (when DIRECT=1):
  Grafana                    http://localhost:3000/
  Prometheus                 http://localhost:9090/
  Alertmanager               http://localhost:9093/
  Blackbox Exporter          http://localhost:9115/
  Pushgateway                http://localhost:9091/

Variables:
  DIRECT                     Set to 1 to run without Caddy and publish direct component ports
  COMPOSE                    Compose command, defaults to docker compose
  COMPOSE_DIRECT             Compose command for DIRECT=1, defaults to docker compose -f docker-compose.yml -f docker-compose.no-caddy.yml
  UV                         Python project manager, defaults to uv
  PYTHON                     Python command for helper scripts, defaults to uv run python
  HADOLINT                   Dockerfile linter, defaults to hadolint
  FILE_SD_HOSTS              File-SD hosts input, defaults to tools/file_sd/hosts
  FILE_SD_TEMPLATE_DIR       File-SD template directory, defaults to tools/file_sd/templates
  FILE_SD_OUT                File-SD renderer output, defaults to docker/prometheus/file_sd
  CADDY_HTTP_PORT            Caddy entry port, defaults to 9000
  GRAFANA_PORT               Direct Grafana port, defaults to 3000
  PROMETHEUS_PORT            Direct Prometheus port, defaults to 9090
  ALERTMANAGER_PORT          Direct Alertmanager port, defaults to 9093
  BLACKBOX_EXPORTER_PORT     Direct Blackbox Exporter port, defaults to 9115
  PUSHGATEWAY_PORT           Direct Pushgateway port, defaults to 9091
  SMOKEPING_KIT_IPV6_SUBNET  Docker IPv6 subnet, defaults to fd42:2428:2428::/64
  SMOKEPING_KIT_PULL_POLICY  Image pull policy, defaults to always in .env.example
  GRAFANA_ADMIN_USER         Grafana admin user, defaults to admin in .env.example
  GRAFANA_ADMIN_PASSWORD     Grafana admin password, defaults to changeme in .env.example
  GRAFANA_PLUGINS            Grafana plugins, defaults to grafana-polystat-panel in .env.example

Examples:
  make up                    # start the normal Caddy stack
  make up DIRECT=1           # start without Caddy and expose direct ports
  make validate              # validate all generated config files
  make render                # render FILE_SD_HOSTS into Prometheus file-SD
  make reload                # reload Prometheus
  make logs                  # follow logs for the default stack
```

## License

This project is released under [The Unlicense](LICENSE).
