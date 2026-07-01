.PHONY: init format lint typecheck test run clean dev-api

init:
	pip install -r requirements.txt
	playwright install chromium
	PYTHONPATH=. python -m src.naukri_agent.main init

format:
	black src tests
	ruff check src tests --select I --fix

lint:
	ruff check src tests

typecheck:
	PYTHONPATH=. mypy src

test:
	PYTHONPATH=. pytest tests -v

run:
	PYTHONPATH=. python -m src.naukri_agent.main run

dev-api:
	cd .. && python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 --loop backend.loop:create_event_loop

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache
