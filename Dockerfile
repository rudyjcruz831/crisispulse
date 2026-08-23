FROM python:3.13.15-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build
COPY requirements.runtime.txt ./
RUN pip install --no-cache-dir --target=/opt/python -r requirements.runtime.txt
COPY pipelines /stage/app/pipelines
COPY data/sample /stage/app/data/sample
RUN mkdir -p /stage/app/data/clean

FROM gcr.io/distroless/python3-debian13:nonroot

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/python

WORKDIR /app
COPY --from=builder /opt/python /opt/python
COPY --chown=10001:10001 --from=builder /stage/app /app
USER 10001:10001

ENTRYPOINT ["/usr/bin/python3"]
CMD ["-m", "pipelines.clean_gkg", "--input", "data/sample/gkg_sample.tsv", "--output", "data/clean/flood_articles.parquet", "--disaster", "flood"]
