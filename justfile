set shell := ["powershell.exe", "-c"]

sync:
    uv sync

console:
	uv run textual console -x EVENT -x SYSTEM

dev:
    uv run textual run --dev src/picolynx/__main__.py
