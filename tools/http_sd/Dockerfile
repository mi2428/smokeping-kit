FROM python:3-alpine

WORKDIR /app

ENV HTTP_SD_HOST=0.0.0.0
ENV HTTP_SD_PORT=8080
ENV PYTHONDONTWRITEBYTECODE=1

COPY tools/http_sd /app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).read()"

CMD ["python", "/app/server.py"]
