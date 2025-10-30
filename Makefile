.PHONY: help install install-dev test lint format type-check clean build dist

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install the package
	pip install -e .

install-dev: ## Install the package with development dependencies
	pip install -e ".[dev]"

test: ## Run tests
	pytest

test-cov: ## Run tests with coverage
	pytest --cov=systemd_monitor --cov-report=html --cov-report=term-missing

lint: ## Run linting checks
	flake8 systemd_monitor/ tests/

format: ## Format code with black
	black systemd_monitor/ tests/

type-check: ## Run type checking
	mypy systemd_monitor/

check: format lint type-check test ## Run all code quality checks

clean: ## Clean build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete

build: ## Build the package
	python setup.py build

dist: clean build ## Create distribution packages
	python setup.py sdist bdist_wheel

install-hooks: ## Install pre-commit hooks
	pre-commit install

create-config: ## Create a default configuration file
	python -m systemd_monitor --create-config config.json

run: ## Run the systemd monitor
	systemd-monitor

run-debug: ## Run the systemd monitor with debug logging
	systemd-monitor --debug
