SHELL         := /bin/bash
.SHELLFLAGS   := -eu -o pipefail -c
.DEFAULT_GOAL := help

APP    := smokeping-kit
DOCKER ?= docker
COMPOSE ?= $(shell if $(DOCKER) compose version >/dev/null 2>&1; then printf '%s compose' '$(DOCKER)'; elif command -v docker-compose >/dev/null 2>&1; then command -v docker-compose; else printf '%s compose' '$(DOCKER)'; fi)
CURL   ?= curl
UV     ?= uv
PYTHON ?= $(UV) run python
HADOLINT ?= $(shell if command -v hadolint >/dev/null 2>&1; then printf 'hadolint'; else printf '%s run --rm -i hadolint/hadolint:latest hadolint' '$(DOCKER)'; fi)

DIRECT ?= 0
CADDY_HTTP_PORT        ?= 9000
PROMETHEUS_PORT        ?= 9090
PUSHGATEWAY_PORT       ?= 9091
ALERTMANAGER_PORT      ?= 9093
BLACKBOX_EXPORTER_PORT ?= 9115
GRAFANA_PORT           ?= 3000

ifneq (,$(wildcard .env))
include .env
export
endif

COMPOSE_DIRECT ?= $(COMPOSE) -f docker-compose.yml -f docker-compose.no-caddy.yml
COMPOSE_FILES := -f docker-compose.yml
FILE_SD_HOSTS ?= tools/file_sd/hosts
FILE_SD_TEMPLATE_DIR ?= tools/file_sd/templates
FILE_SD_OUT ?= docker/prometheus/file_sd
HELP_LABEL_WIDTH := 26

ifeq ($(DIRECT),1)
COMPOSE_FILES += -f docker-compose.no-caddy.yml
endif

STACK_COMPOSE := $(COMPOSE) $(COMPOSE_FILES)

##@ Stack

.PHONY: up
up: ## Start the stack. Set DIRECT=1 to publish component ports directly
ifeq ($(DIRECT),1)
	@$(COMPOSE) rm -sf caddy
	@$(STACK_COMPOSE) up -d --remove-orphans
else
	@$(STACK_COMPOSE) up -d
endif

.PHONY: down
down: ## Stop and remove the stack. Set DIRECT=1 for direct port mode
	@$(STACK_COMPOSE) down

.PHONY: restart
restart: ## Restart running services
	@$(STACK_COMPOSE) restart

.PHONY: pull
pull: ## Pull latest service images
	@$(STACK_COMPOSE) pull

.PHONY: ps
ps: ## Show service status. Set DIRECT=1 for direct port mode
	@$(STACK_COMPOSE) ps

.PHONY: logs
logs: ## Follow logs. Set DIRECT=1 for direct port mode
	@$(STACK_COMPOSE) logs -f --tail=200

##@ Operations

.PHONY: validate
validate: ## Validate Compose, Caddy, Blackbox, Prometheus, and Alertmanager config
	@$(COMPOSE) config >/dev/null
	@$(COMPOSE_DIRECT) config >/dev/null
	@$(PYTHON) tools/file_sd/render.py --hosts "$(FILE_SD_HOSTS)" --template-dir "$(FILE_SD_TEMPLATE_DIR)" --out-dir "$(FILE_SD_OUT)" --check
	@$(PYTHON) -m unittest tools/file_sd/render_test.py
	@$(PYTHON) tools/http_sd/server.py --check
	@$(PYTHON) -m unittest tools/http_sd/server_test.py
	@$(HADOLINT) - < tools/http_sd/Dockerfile
	@awk 'BEGIN { bad = 0 } /^receivers:/ { in_receivers = 1 } in_receivers && /^#/ { printf "bad receiver comment indent: %s:%d:%s\n", FILENAME, FNR, $$0; bad = 1 } END { exit bad }' docker/alertmanager/alertmanager.yml
	@$(DOCKER) run --rm -v "$$(pwd)/docker/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:latest caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
	@$(DOCKER) run --rm -v "$$(pwd)/docker/blackbox/blackbox.yml:/etc/blackbox_exporter/blackbox.yml:ro" prom/blackbox-exporter:latest --config.file=/etc/blackbox_exporter/blackbox.yml --config.check
	@$(DOCKER) run --rm --entrypoint promtool -v "$$(pwd)/docker/prometheus:/etc/prometheus:ro" prom/prometheus:latest check config /etc/prometheus/prometheus.yml
	@$(DOCKER) run --rm --entrypoint amtool -v "$$(pwd)/docker/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro" prom/alertmanager:latest check-config /etc/alertmanager/alertmanager.yml

.PHONY: check
check: validate ## Alias for validate

.PHONY: render
render: ## Render file-SD target YAML from FILE_SD_HOSTS
	@$(PYTHON) tools/file_sd/render.py --hosts "$(FILE_SD_HOSTS)" --template-dir "$(FILE_SD_TEMPLATE_DIR)" --out-dir "$(FILE_SD_OUT)"

.PHONY: reload
reload: ## Reload Prometheus, auto-detecting Caddy when available
	@if [ -n "$$($(COMPOSE) ps -q caddy 2>/dev/null)" ]; then \
		url="http://localhost:$(CADDY_HTTP_PORT)/prometheus/-/reload"; \
	else \
		url="http://localhost:$(PROMETHEUS_PORT)/-/reload"; \
	fi; \
	$(CURL) -fsS -X POST "$$url"

.PHONY: clean
clean: ## Stop the stack and remove volumes. Set DIRECT=1 for direct port mode
	@$(STACK_COMPOSE) down -v

##@ Help

.PHONY: help
help: ## Show this help message
	@awk 'BEGIN {FS = ":.*##"; width = 0} \
		{ lines[NR] = $$0 } \
		/^[a-zA-Z0-9_.-]+:.*##/ { if (length($$1) > width) width = length($$1) } \
		END { \
			section = ""; \
			width += 2; \
			for (i = 1; i <= NR; i++) { \
				$$0 = lines[i]; \
				if ($$0 ~ /^##@/) { \
					section = substr($$0, 5); \
				} else if ($$0 ~ /^[a-zA-Z0-9_.-]+:.*##/) { \
					split($$0, parts, ":.*##"); \
					if (section != "") printf "\n\033[1m%s\033[0m\n", section; \
					section = ""; \
					printf "  \033[36m%-*s\033[0m %s\n", width, parts[1], parts[2]; \
				} \
			} \
		}' $(MAKEFILE_LIST)
	@printf "\n\033[1;36mCaddy URLs:\033[0m\n"
	@awk -v port="$(CADDY_HTTP_PORT)" -v width="$(HELP_LABEL_WIDTH)" '\
		function label(service) { \
			if (service == "blackbox-exporter") return "Blackbox Exporter"; \
			if (service == "http-sd") return "HTTP-SD"; \
			if (service == "pushgateway") return "Pushgateway"; \
			if (service == "alertmanager") return "Alertmanager"; \
			if (service == "prometheus") return "Prometheus"; \
			if (service == "grafana") return "Grafana"; \
			return service; \
		} \
		$$1 ~ /^handle/ { route = $$2; sub(/\/\*$$/, "/", route); pending = route } \
		pending != "" && $$1 == "reverse_proxy" { service = $$2; sub(/:.*/, "", service); printf "  \033[36m%-*s\033[0m http://localhost:%s%s\n", width, label(service), port, pending; pending = "" } \
	' docker/caddy/Caddyfile
	@printf "\n\033[1;36mDirect URLs (when DIRECT=1):\033[0m\n"
	@awk -v width="$(HELP_LABEL_WIDTH)" -v ports="GRAFANA_PORT=$(GRAFANA_PORT) PROMETHEUS_PORT=$(PROMETHEUS_PORT) ALERTMANAGER_PORT=$(ALERTMANAGER_PORT) BLACKBOX_EXPORTER_PORT=$(BLACKBOX_EXPORTER_PORT) PUSHGATEWAY_PORT=$(PUSHGATEWAY_PORT)" '\
		BEGIN { \
			split(ports, pairs, " "); \
			for (i in pairs) { split(pairs[i], kv, "="); port_values[kv[1]] = kv[2] } \
		} \
		function label(service) { \
			if (service == "blackbox-exporter") return "Blackbox Exporter"; \
			if (service == "pushgateway") return "Pushgateway"; \
			if (service == "alertmanager") return "Alertmanager"; \
			if (service == "prometheus") return "Prometheus"; \
			if (service == "grafana") return "Grafana"; \
			return service; \
		} \
		/^  [A-Za-z0-9_-]+:/ { service = $$1; sub(/:/, "", service) } \
		/^[[:space:]]+- "\$$\{[A-Z0-9_]+:-[0-9]+\}:[0-9]+"/ { \
			line = $$0; \
			sub(/^.*\$$\{/, "", line); \
			sub(/\}.*/, "", line); \
			split(line, parts, ":-"); \
			port = port_values[parts[1]]; \
			if (port == "") port = parts[2]; \
			urls[service] = sprintf("http://localhost:%s/", port); \
		} \
		END { \
			order[1] = "grafana"; \
			order[2] = "prometheus"; \
			order[3] = "alertmanager"; \
			order[4] = "blackbox-exporter"; \
			order[5] = "pushgateway"; \
			for (i = 1; i <= 5; i++) { \
				service = order[i]; \
				if (service in urls) printf "  \033[36m%-*s\033[0m %s\n", width, label(service), urls[service]; \
			} \
		} \
	' docker-compose.no-caddy.yml
	@printf "\n\033[1;36mVariables:\033[0m\n"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Set to \033[36m1\033[0m to run without Caddy and publish direct component ports\n" "DIRECT"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Compose command, defaults to \033[36m%s\033[0m\n" "COMPOSE" "$(COMPOSE)"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Compose command for DIRECT=1, defaults to \033[36m%s\033[0m\n" "COMPOSE_DIRECT" "$(COMPOSE_DIRECT)"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Python project manager, defaults to \033[36m%s\033[0m\n" "UV" "$(UV)"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Python command for helper scripts, defaults to \033[36m%s\033[0m\n" "PYTHON" "$(PYTHON)"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Dockerfile linter, defaults to \033[36m%s\033[0m\n" "HADOLINT" "$(HADOLINT)"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m File-SD hosts input, defaults to \033[36m%s\033[0m\n" "FILE_SD_HOSTS" "$(FILE_SD_HOSTS)"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m File-SD template directory, defaults to \033[36m%s\033[0m\n" "FILE_SD_TEMPLATE_DIR" "$(FILE_SD_TEMPLATE_DIR)"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m File-SD renderer output, defaults to \033[36m%s\033[0m\n" "FILE_SD_OUT" "$(FILE_SD_OUT)"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Caddy entry port, defaults to \033[36m%s\033[0m\n" "CADDY_HTTP_PORT" "$(CADDY_HTTP_PORT)"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Direct Grafana port, defaults to \033[36m%s\033[0m\n" "GRAFANA_PORT" "$(GRAFANA_PORT)"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Direct Prometheus port, defaults to \033[36m%s\033[0m\n" "PROMETHEUS_PORT" "$(PROMETHEUS_PORT)"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Direct Alertmanager port, defaults to \033[36m%s\033[0m\n" "ALERTMANAGER_PORT" "$(ALERTMANAGER_PORT)"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Direct Blackbox Exporter port, defaults to \033[36m%s\033[0m\n" "BLACKBOX_EXPORTER_PORT" "$(BLACKBOX_EXPORTER_PORT)"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Direct Pushgateway port, defaults to \033[36m%s\033[0m\n" "PUSHGATEWAY_PORT" "$(PUSHGATEWAY_PORT)"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Image pull policy, defaults to \033[36malways\033[0m in .env.example\n" "SMOKEPING_KIT_PULL_POLICY"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Grafana admin user, defaults to \033[36madmin\033[0m in .env.example\n" "GRAFANA_ADMIN_USER"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Grafana admin password, defaults to \033[36mchangeme\033[0m in .env.example\n" "GRAFANA_ADMIN_PASSWORD"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m Grafana plugins, defaults to \033[36mgrafana-polystat-panel\033[0m in .env.example\n" "GRAFANA_PLUGINS"
	@printf "\n\033[1;36mExamples:\033[0m\n"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m # start the normal Caddy stack\n" "make up"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m # start without Caddy and expose direct ports\n" "make up DIRECT=1"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m # validate all generated config files\n" "make validate"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m # render FILE_SD_HOSTS into Prometheus file-SD\n" "make render"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m # reload Prometheus\n" "make reload"
	@printf "  \033[36m%-$(HELP_LABEL_WIDTH)s\033[0m # follow logs for the default stack\n" "make logs"
