.PHONY: dev backend-dev frontend-dev test backend-test frontend-test lint typecheck migrate seed e2e

dev:
	$(MAKE) backend-dev

backend-dev:
	cd backend && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-dev:
	cd frontend && npm run dev

test: backend-test frontend-test

backend-test:
	cd backend && python -m pytest

frontend-test:
	cd frontend && npm test

lint:
	cd backend && python -m ruff check app tests
	cd frontend && npm run lint

typecheck:
	cd backend && python -m mypy app
	cd frontend && npm run typecheck

migrate:
	cd backend && python -m alembic upgrade head

seed:
	cd backend && python -m app.db.seed

e2e:
	cd frontend && npm run e2e
