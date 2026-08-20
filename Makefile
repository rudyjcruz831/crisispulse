.PHONY: setup sample counts batch test docker-sample docker-live docker-window

setup:
	python -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt

sample:
	.venv/bin/python -m pipelines.clean_gkg --input data/sample/gkg_sample.tsv --output data/clean/flood_articles.parquet --disaster flood
	.venv/bin/python -m pipelines.hourly_counts --input data/clean/flood_articles.parquet

counts:
	.venv/bin/python -m pipelines.hourly_counts --input data/clean/flood_articles.parquet

batch:
	.venv/bin/python -m pipelines.batch_clean --input-dir data/raw --output data/clean/flood_articles_batch.parquet --disaster flood --minimum-strength weak
	.venv/bin/python -m pipelines.build_review_set --input data/clean/flood_articles_batch.parquet --output data/review/flood_manual_review.csv --size 40
	.venv/bin/python -m pipelines.build_features --input data/clean/flood_articles_batch.parquet --output data/features/hourly_region_features.parquet
	.venv/bin/python -m pipelines.inspect_features --input data/features/hourly_region_features.parquet --output data/features/hourly_region_report.json

test:
	.venv/bin/python -m pytest

docker-sample:
	docker compose run --rm pipeline

docker-live:
	docker compose --profile live run --rm ingestor

docker-window:
	docker compose --profile live run --rm ingestor --intervals 8 --output-dir /app/data/raw
