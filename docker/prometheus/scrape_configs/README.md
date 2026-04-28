# Scrape Configs

Prometheus loads `*.yml` files from this directory through `scrape_config_files` in `docker/prometheus/prometheus.yml`.

`http_sd.yml` is active by default.
The matching HTTP SD app returns no targets until `tools/http_sd/server.py` is customized, so the default stack stays quiet.
