# Every recipe lives in scripts/dev.py so it behaves the same on Windows, macOS and Linux.
# Without make: `python scripts/dev.py <target>` (python3 on macOS/Linux).

ifeq ($(OS),Windows_NT)
PY ?= python
else
PY ?= python3
endif
RUN = $(PY) scripts/dev.py

.PHONY: setup server lab demo tunnel test test-web e2e lint types explainers

setup:     ## venv + server deps, npm ci for all workspaces, model files
	$(RUN) setup
server:    ## FastAPI on :8000
	$(RUN) server
lab:       ## Lab site on :5173
	$(RUN) lab
demo:      ## Demo site on :5174
	$(RUN) demo
tunnel:    ## cloudflared HTTPS tunnels for :5173 and :5174
	$(RUN) tunnel
test:      ## pytest
	$(RUN) test
test-web:  ## tsc + vitest for every workspace
	$(RUN) test-web
e2e:       ## Playwright, Chromium with a fake camera
	$(RUN) e2e
lint:      ## ruff + eslint
	$(RUN) lint
types:     ## regenerate packages/types from server/pulselens/models.py
	$(RUN) types
explainers: ## regenerate packages/explain from docs/EXPLAINERS.md
	$(RUN) explainers
