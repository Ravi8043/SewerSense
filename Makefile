# Convenience targets. On Windows without make, run the commands shown in README.md directly.
ifeq ($(OS),Windows_NT)
PY := backend/.venv/Scripts/python.exe
else
PY := backend/.venv/bin/python
endif

.PHONY: install seed backend frontend test typecheck build

install:            ## install backend and frontend dependencies (does not upgrade pip)
	$(PY) -m pip install --disable-pip-version-check -r backend/requirements.txt
	npm --prefix frontend install

seed:               ## rebuild the demo database from the synthetic baseline
	cd backend && ../$(PY) seed.py

backend:            ## API on http://localhost:8000
	$(PY) -m uvicorn app.main:app --app-dir backend --port 8000

frontend:           ## command center on http://localhost:5173
	npm --prefix frontend run dev

test:               ## backend test suite (no API key or network needed)
	cd backend && ../$(PY) -m pytest -q

typecheck:
	npm --prefix frontend run typecheck

build:
	npm --prefix frontend run build
