# File-SD Renderer

This optional helper generates Prometheus file service discovery YAML from an `/etc/hosts`-style file.

It deliberately uses only Python standard library modules.
The input is hosts format, the template is `string.Template`, and the output is Prometheus file-SD YAML.
Python execution is managed by `uv` through the repository `pyproject.toml`.

Preview generated files:

```console
$ make render
```

Write generated files into the active Prometheus file-SD directory:

```console
$ make render FILE_SD_OUT=docker/prometheus/file_sd
$ make reload
```

Use your own hosts file:

```console
$ make render FILE_SD_HOSTS=targets.hosts FILE_SD_OUT=docker/prometheus/file_sd
```

Input shape:

```text
93.184.216.34 example.com # probe=httping group=examples
93.184.216.34 example.com # probe=tcping group=examples port=443
127.0.0.11 docker-dns # probe=dns group=docker dns_query=example.com
```

Supported probe values include `icmp`, `httping`, `http_get_body`, `https_cert`, `tcping`, `tcp_tls`, and `dns`.
Use `target=...` to override the generated target.

Keep the generated labels aligned with the scrape jobs in `docker/prometheus/prometheus.yml` and the modules in `docker/blackbox/blackbox.yml`.
