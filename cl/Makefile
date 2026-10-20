.PHONY: install run test lint docker
install:
	pip install -e ".[dev]"
run:
	USE_MOCK_AI=1 uvicorn careloop.main:create --factory --reload --port 8000
test:
	pytest
lint:
	ruff check .
docker:
	docker build -t careloop . && docker run -p 8000:8000 -e USE_MOCK_AI=1 careloop
