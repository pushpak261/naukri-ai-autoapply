.PHONY: init format lint typecheck test run clean

init:
	pip install -r requirements.txt

format:
	black src/ tests/
	isort src/ tests/

lint:
	ruff check src/ tests/

typecheck:
	mypy src/

test:
	pytest tests/ -v

run:
	python -m src.main run

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
