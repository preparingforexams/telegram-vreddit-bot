.PHONY: check
check: lint test

.PHONY: lint
lint:
	uv run ruff format src/
	uv run ruff check --fix --show-fixes src/
	uv run pyright src/

.PHONY: test
test:
	uv run pytest src/
