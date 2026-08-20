FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pipelines ./pipelines
COPY data/sample ./data/sample

CMD ["python", "-m", "pipelines.clean_gkg", "--input", "data/sample/gkg_sample.tsv", "--output", "data/clean/flood_articles.parquet", "--disaster", "flood"]
