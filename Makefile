.PHONY: help test coverage lint format typecheck clean install build publish release-dry _check-uv

SRC := $(filter-out tests,$(patsubst %/__init__.py,%,$(wildcard */__init__.py)))

help:
	@echo "pystou - Python scripts for deduplicating folders and unarchiving files"
	@echo ""
	@echo "Usage:"
	@echo "  make install        Sync the uv environment with dev extras"
	@echo "  pystou dedup DIR    Find and deduplicate duplicate folders"
	@echo "  pystou extract DIR  Extract archive files"
	@echo "  pystou cleanup DIR  Remove junk files (.DS_Store, Thumbs.db, ...)"
	@echo "  pystou identify DIR Identify file types and detect issues"
	@echo "  pystou stats DIR    Show directory statistics"
	@echo "  pystou empty DIR    Find and remove empty directories"
	@echo ""
	@echo "Development:"
	@echo "  make test           Run the test suite"
	@echo "  make coverage       Run tests with coverage report"
	@echo "  make lint           Check code style"
	@echo "  make format         Auto-format code"
	@echo "  make typecheck      Run mypy"
	@echo "  make clean          Remove cache and build files"
	@echo ""
	@echo "Release:"
	@echo "  make build          Build sdist and wheel into dist/"
	@echo "  make publish        Build and upload to PyPI (needs a token)"
	@echo "  make release-dry    Preview the next semantic-release version"

_check-uv:
	@command -v uv >/dev/null 2>&1 || { \
		echo "Error: uv is not installed"; \
		echo ""; \
		echo "Install it from https://docs.astral.sh/uv/getting-started/installation/"; \
		exit 1; \
	}

test: _check-uv
	@uv run --extra dev pytest tests -v

coverage: _check-uv
	@uv run --extra dev pytest --cov=. --cov-report=term-missing tests

lint: _check-uv
	@uv run --extra dev ruff check $(SRC) tests && uv run --extra dev ruff format --check $(SRC) tests && echo "Lint OK"

format: _check-uv
	@uv run --extra dev ruff check --fix $(SRC) tests && uv run --extra dev ruff format $(SRC) tests && echo "Format OK"

typecheck: _check-uv
	@uv run --extra dev mypy $(SRC) && echo "Typecheck OK"

clean:
	@rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	@rm -rf dist build pystou.egg-info
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@echo "Cleaned"

install: _check-uv
	@uv sync --extra dev
	@echo "Synced pystou environment with dev extras"

build: _check-uv
	@rm -rf dist build pystou.egg-info
	@uv build
	@echo ""
	@echo "Built artifacts:"
	@ls -1 dist

publish: build
	@uv publish
	@echo "Published to PyPI"

release-dry: _check-uv
	@uvx --from python-semantic-release semantic-release version --print
