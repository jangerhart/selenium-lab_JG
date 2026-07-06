.PHONY: install lint typecheck test check

install:
	python -m pip install -e ".[dev]"

lint:
	ruff check .

typecheck:
	mypy src

test:
	pytest

check: lint typecheck test

