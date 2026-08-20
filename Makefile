.PHONY: setup sample counts test docker-sample docker-live

setup:
	python -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt

sample:
	.venv/bin/python -m pipelines.clean_gkg --input data/sample/gkg_sample.tsv --output data/clean/flood_articles.parquet --disaster flood
	.venv/bin/python -m pipelines.hourly_counts --input data/clean/flood_articles.parquet

counts:
	.venv/bin/python -m pipelines.hourly_counts --input data/clean/flood_articles.parquet

test:
	.venv/bin/python -m pytest

docker-sample:
	docker compose run --rm pipeline

docker-live:
	docker compose --profile live run --rm ingestor
