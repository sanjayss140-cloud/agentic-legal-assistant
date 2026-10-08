.PHONY: run test install clean

run:
	python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload

test:
	pytest -v backend/tests/

install:
	python -m pip install -r requirements.txt

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
