set shell := ["powershell.exe", "-c"]

sync:
    uv sync

activate:
    . .\.venv\Scripts\activate

console:
	uv run textual console -x EVENT -x SYSTEM

dev:
    uv run textual run --dev src/picolynx/__main__.py

test:
    uv run pytest --cov=picolynx --cov-report=term-missing -vv

lint:
    uv run ruff format; uv run ruff check --fix