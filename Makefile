.PHONY: help install up down logs build clean example test lint

help:
	@echo "X-Ray SDK & API Development Commands"
	@echo ""
	@echo "Docker:"
	@echo "  make up        - Start PostgreSQL and X-Ray API containers"
	@echo "  make down      - Stop all containers"
	@echo "  make logs      - Follow X-Ray API logs"
	@echo "  make build     - Rebuild Docker images"
	@echo "  make clean     - Stop containers and remove volumes"
	@echo ""
	@echo "Development:"
	@echo "  make install   - Install package in development mode"
	@echo "  make test      - Run test suite"
	@echo "  make lint      - Run linter and type checker"
	@echo ""
	@echo "Examples:"
	@echo "  make example   - Run the recommendation pipeline example"

# Docker commands
up:
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example"; fi
	docker-compose up -d
	@echo ""
	@echo "Services started:"
	@echo "  - PostgreSQL: localhost:5433"
	@echo "  - X-Ray API:  http://localhost:8000"

down:
	docker-compose down

logs:
	docker-compose logs -f xray-api

build:
	docker-compose build

clean:
	docker-compose down -v
	@echo "Containers stopped and volumes removed"

# Development commands
install:
	pip install -e ".[all]"

test:
	pytest

lint:
	ruff check .
	mypy sdk api shared

# Example
example:
	@echo "Running recommendation pipeline example..."
	@echo "Make sure services are running (make up)"
	@echo ""
	cd examples/recommendation-pipeline && pip install -q -r requirements.txt && python main.py
