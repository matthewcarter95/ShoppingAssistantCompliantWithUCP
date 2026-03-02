.PHONY: install dev test build deploy clean local deploy-frontend help venv

# Detect if we're in a virtual environment
VENV_PYTHON := $(shell if [ -f venv/bin/python ]; then echo "venv/bin/python"; elif [ -n "$$VIRTUAL_ENV" ]; then echo "python"; else echo "python3"; fi)
VENV_PIP := $(shell if [ -f venv/bin/pip ]; then echo "venv/bin/pip"; elif [ -n "$$VIRTUAL_ENV" ]; then echo "pip"; else echo "python3 -m pip"; fi)
VENV_UVICORN := $(shell if [ -f venv/bin/uvicorn ]; then echo "venv/bin/uvicorn"; elif [ -n "$$VIRTUAL_ENV" ]; then echo "uvicorn"; else echo "python3 -m uvicorn"; fi)
VENV_PYTEST := $(shell if [ -f venv/bin/pytest ]; then echo "venv/bin/pytest"; elif [ -n "$$VIRTUAL_ENV" ]; then echo "pytest"; else echo "python3 -m pytest"; fi)

help:
	@echo "Available commands:"
	@echo "  make venv             - Create virtual environment"
	@echo "  make install          - Install production dependencies"
	@echo "  make dev              - Install development dependencies"
	@echo "  make test             - Run tests"
	@echo "  make lint             - Run linters"
	@echo "  make format           - Format code with black"
	@echo "  make build            - Build SAM application"
	@echo "  make deploy           - Deploy to AWS"
	@echo "  make deploy-frontend  - Upload frontend to S3"
	@echo "  make local            - Run FastAPI locally"
	@echo "  make clean            - Clean build artifacts"
	@echo ""
	@echo "Note: Commands will use venv/bin/* if available, otherwise system Python"

venv:
	python3 -m venv venv
	@echo "Virtual environment created. Activate with: source venv/bin/activate"

install:
	$(VENV_PIP) install -e .

dev:
	$(VENV_PIP) install -e ".[dev]"

test:
	$(VENV_PYTEST) tests/ -v

lint:
	$(VENV_PYTHON) -m ruff check src/
	$(VENV_PYTHON) -m mypy src/ --ignore-missing-imports

format:
	$(VENV_PYTHON) -m black src/ tests/

build:
	sam build

deploy:
	sam deploy --guided

deploy-frontend:
	@if [ -z "$(FRONTEND_BUCKET)" ]; then \
		echo "Error: FRONTEND_BUCKET not set. Usage: make deploy-frontend FRONTEND_BUCKET=your-bucket-name"; \
		exit 1; \
	fi
	aws s3 sync frontend/ s3://$(FRONTEND_BUCKET)/

local:
	@if [ ! -f venv/bin/uvicorn ] && [ -z "$$VIRTUAL_ENV" ]; then \
		echo "Error: Virtual environment not found or not activated."; \
		echo "Run: source venv/bin/activate"; \
		echo "Or: make venv && source venv/bin/activate && make dev"; \
		exit 1; \
	fi
	$(VENV_UVICORN) src.chatbot.app:app --reload --port 8000

clean:
	rm -rf .aws-sam/
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf venv/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
