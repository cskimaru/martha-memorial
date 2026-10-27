SHELL := /bin/bash
COMPOSE := docker compose
DEV := $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml
SERVICES := auth memorial media web
PY ?= python3

.PHONY: help share share-new share-stop init up down down-apps dev dev-down logs ps migrate create-owner backup-now restore smoke test lint fmt build pull deploy

help:          ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

share:         ## Run on this computer and share it (keeps the current link; your own domain if set up)
	./scripts/share.sh

share-new:     ## Same, but with a fresh quick link
	./scripts/share.sh new

share-stop:    ## Stop the shared copy (data is kept)
	./scripts/share.sh stop

init:          ## Create .env, secrets and generated config (safe to re-run)
	./scripts/init.sh

up:            ## Start the production stack
	$(COMPOSE) up -d --wait

down:          ## Stop everything (data is kept)
	$(COMPOSE) down

down-apps:     ## Stop only the application services (for a restore)
	$(COMPOSE) stop caddy web auth memorial media

pull:          ## Pull the images for IMAGE_TAG
	$(COMPOSE) pull --ignore-buildable

build:         ## Build all images locally
	$(COMPOSE) build

dev:           ## Run locally on http://localhost:8080
	$(DEV) up -d --build --wait

dev-down:
	$(DEV) down

logs:          ## Follow logs (make logs s=memorial)
	$(COMPOSE) logs -f --tail=200 $(s)

ps:
	$(COMPOSE) ps

create-owner:  ## Create the first owner account: make create-owner email=... name=...
	$(COMPOSE) exec -it auth python -m app.cli create-owner --email "$(email)" --name "$(name)"

backup-now:    ## Take a backup immediately
	$(COMPOSE) exec backup backup.sh

restore:       ## Restore: make restore file=backups/archive/<stamp>.tar.gz.gpg
	$(MAKE) down-apps
	$(COMPOSE) run --rm --entrypoint restore.sh backup /backups/archive/$(notdir $(file)) --yes
	$(MAKE) up

smoke:         ## Check a running site: make smoke url=https://martha.example.com
	$(PY) scripts/smoke_test.py $(url)

test:          ## Run every service's test suite
	@set -e; for s in $(SERVICES); do echo "== $$s"; (cd services/$$s && $(PY) -m pytest -q); done

lint:          ## Lint and check formatting
	ruff check . && ruff format --check .

fmt:
	ruff format . && ruff check --fix .
