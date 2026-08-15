# The nvm default on this machine is Node 22.10, which pnpm 11 refuses.
export PATH := /opt/homebrew/opt/node/bin:$(PATH)

WEB := cd apps/web &&

.PHONY: help install dev api web test test-all test-py test-ts test-e2e test-kokoro docs lint
help:  ## Show this help
	@grep -hE '^[a-z0-9-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | expand -t20

install:  ## Install everything, including the Kokoro model extra
	uv sync --extra tts
	$(WEB) pnpm install
	uv run playwright install chromium

# Ctrl-C otherwise leaves uvicorn holding port 8000, breaking the next run. Kill
# by *port*: `$$!` is just the `uv run` wrapper (uvicorn is its child and
# outlives it), a name match misses it, and `kill 0` would kill the caller too.
dev:  ## Run the API and the web app together
	@uv run --extra tts uvicorn reader.app:create_app --factory --reload --port 8000 & \
	trap 'lsof -ti tcp:8000 -sTCP:LISTEN | xargs kill 2>/dev/null' EXIT INT TERM; \
	$(WEB) pnpm dev

api:  ## Run just the API, with the real Kokoro model
	uv run --extra tts uvicorn reader.app:create_app --factory --reload --port 8000

web:  ## Run just the web app
	$(WEB) pnpm dev

test: test-py test-ts  ## Everything that does not need a browser or the model

test-py:  ## Python: properties, services, contract
	uv run pytest -q -m "not docs and not kokoro"

test-all:  ## Every test there is, including the browser and the real model
	uv run --extra tts pytest -q

test-ts:  ## TypeScript: Hegel properties and component tests
	$(WEB) pnpm test

test-e2e:  ## Browser scenarios; regenerates the documentation screenshots
	uv run pytest -q -m docs

test-kokoro:  ## The one test that exercises the real model
	uv run --extra tts pytest -q -m kokoro

docs:  ## Build the Diataxis site (needs test-e2e to have run first)
	uv run python scripts/gen_behaviours.py
	uv run mkdocs build --strict

lint:  ## Ruff over the Python, tsc over the TypeScript
	uv run ruff check .
	$(WEB) pnpm exec tsc -b
