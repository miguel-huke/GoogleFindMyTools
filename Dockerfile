# syntax=docker/dockerfile:1

FROM python:3.12.15-slim-bookworm

LABEL org.opencontainers.image.title="GoogleFindMyTools Map" \
      org.opencontainers.image.description="Local Find Hub map with SQLite persistence" \
      org.opencontainers.image.licenses="GPL-3.0-only"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    GFMT_MODE=demo \
    GFMT_BIND_HOST=0.0.0.0 \
    GFMT_PORT=8765 \
    GFMT_DATABASE_PATH=/data/find_hub.db \
    GFMT_ALLOW_NON_LOOPBACK=true \
    GFMT_TRUSTED_HOSTS=127.0.0.1:8765,localhost:8765 \
    GFMT_TRUSTED_ORIGINS=http://127.0.0.1:8765,http://localhost:8765

WORKDIR /app

RUN groupadd --gid 10001 gfmt \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/gfmt gfmt

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --requirement requirements.txt

COPY Auth ./Auth
COPY FMDNCrypto ./FMDNCrypto
COPY KeyBackup ./KeyBackup
COPY MapApp ./MapApp
COPY NovaApi ./NovaApi
COPY ProtoDecoders ./ProtoDecoders
COPY SpotApi ./SpotApi
COPY migrations ./migrations
COPY scripts ./scripts
COPY tests ./tests
COPY Dockerfile compose.yaml .dockerignore ./
COPY main.py chrome_driver.py example_data_provider.py ./
COPY LICENSE CITATION.cff THIRD_PARTY_NOTICES.md ./

RUN mkdir -p /data /state/auth \
    && ln -s /state/auth/secrets.json /app/Auth/secrets.json \
    && chown -R 10001:10001 /data /state/auth /home/gfmt

USER 10001:10001

EXPOSE 8765
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/v1/health', timeout=2).read()"]

CMD ["python", "-B", "main.py", "--no-browser"]
