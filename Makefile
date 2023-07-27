.PHONY: nice

nice:
	poetry run black src/
	poetry run flake8 --exit-zero src/
	poetry run isort src/
	poetry run mypy src/
