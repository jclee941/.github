.PHONY: test test-unit test-e2e test-live lint install clean

install:
	python3.12 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e .

test-unit:
	.venv/bin/python -m pytest tests/unittest -v

test-e2e:
	.venv/bin/python -m pytest tests/e2e -v --tb=short

test-live:
	.venv/bin/python -m pytest tests/e2e_live -v --tb=short

test: test-unit test-e2e test-live

lint:
	.venv/bin/python -m ruff check .

clean:
	rm -rf .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
