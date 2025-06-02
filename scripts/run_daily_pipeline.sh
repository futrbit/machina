#!/usr/bin/env bash
set -euo pipefail
source "$(dirname $0)/../.venv/bin/activate"
python -m pipelines.news_fetcher
python -m pipelines.summarizer
python -m pipelines.exporter