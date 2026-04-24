.PHONY: dev test deploy logs migrate backup-db

dev:
	pip install -r requirements-dev.txt
	python -m src.main

test:
	pytest tests/ -v --asyncio-mode=auto

deploy:
	docker-compose -f docker/docker-compose.yml up -d --build

stop:
	docker-compose -f docker/docker-compose.yml down

logs:
	docker-compose -f docker/docker-compose.yml logs -f bot

migrate:
	DATABASE_URL=$$(grep DATABASE_URL .env | cut -d= -f2) alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(msg)"

backup-db:
	docker-compose -f docker/docker-compose.yml exec db \
		pg_dump -U botuser telegrambot > backup_$$(date +%Y%m%d_%H%M%S).sql
