PY ?= python

.PHONY: install train eval snapshot api web test all

install:
	$(PY) -m pip install -r requirements-dev.txt
	cd frontend && npm install

train:
	$(PY) -m src.train

eval:
	$(PY) -m src.evaluate

snapshot:
	$(PY) -m src.export_snapshot

api:
	$(PY) -m uvicorn src.api:app --reload --port 8000

web:
	cd frontend && npm run dev

test:
	$(PY) -m pytest -q

all: train eval snapshot test
