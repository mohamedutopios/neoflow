# NeoFlow : commandes courantes. `make` ou `make help` affiche la liste.
SHELL := /bin/bash
COMPOSE ?= docker compose
.DEFAULT_GOAL := help

.PHONY: help up up-ia down infra backend backend-h2 frontend test test-backend test-frontend e2e lint labs-test labs-offline regression-on regression-off

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

up: ## Démarre toute la stack docker (postgres, jaeger, backend :8080, frontend :5173)
	$(COMPOSE) up -d --build

up-ia: ## Démarre en plus qdrant et ollama (profil ia, laboratoires J05-J06)
	$(COMPOSE) --profile ia up -d --build

down: ## Arrête la stack (tous profils), volumes conservés
	$(COMPOSE) --profile ia down

infra: ## Démarre seulement postgres et jaeger (pour make backend)
	$(COMPOSE) up -d postgres jaeger

backend: ## Lance le backend en local, profil dev (PostgreSQL docker : make infra)
	cd backend && ./mvnw spring-boot:run -Dspring-boot.run.profiles=dev

backend-h2: ## Lance le backend en local sans Docker, profil dev-h2 (H2 en mémoire)
	cd backend && ./mvnw spring-boot:run -Dspring-boot.run.profiles=dev-h2

frontend: ## Lance le frontend Vite sur http://localhost:5173 (proxy /api vers :8080)
	cd frontend && { [ -d node_modules ] || npm ci; } && npm run dev

test: test-backend test-frontend ## Tests backend (unitaires + intégration) et frontend

test-backend: ## Tests backend : ./mvnw verify (DemandeServiceTest, RegleMetierRegistryTest, DemandeControllerIT)
	cd backend && ./mvnw -B verify

test-frontend: ## Tests frontend (Vitest)
	cd frontend && { [ -d node_modules ] || npm ci; } && npm test

e2e: ## Tests de bout en bout Playwright (backend et frontend démarrés)
	cd e2e && { [ -d node_modules ] || npm ci; } && npx playwright install chromium && npx playwright test

lint: ## ESLint et vérification de types du frontend, compilation du backend
	cd frontend && { [ -d node_modules ] || npm ci; } && npm run lint && npm run typecheck
	cd backend && ./mvnw -B -q -DskipTests compile

labs-test: ## Tests des laboratoires présents (labs/<lab>/), labs absents ou sans tests ignorés ; LABS="rag mcp" pour filtrer
	./scripts/labs.sh test

labs-offline: ## Tests des laboratoires sans clé API (mode offline) + fumée de neoagent --offline
	./scripts/labs.sh offline

regression-on: ## Injecte la régression du TP J07
	./scripts/injecter-regression.sh

regression-off: ## Retire la régression du TP J07
	./scripts/retirer-regression.sh
