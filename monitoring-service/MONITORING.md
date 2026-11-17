# Monitoring Service

Monitoring Service владеет каталогом товаров, предложениями конкурентов, процессом сбора данных и историей конкурентных цен в Moncure. Сервис преобразует результаты Collector в надёжное текущее состояние и публикует версионированные изменения для Pricing.

## Границы ответственности

Monitoring владеет:

- товарами организаций;
- предложениями конкурентов, привязанными к одному товару;
- заданиями импорта и данными для ручного подтверждения;
- пакетами сбора и отдельными заданиями по предложениям;
- текущим состоянием конкурентов и неизменяемой историей наблюдений;
- RabbitMQ Inbox и Outbox.

Monitoring не владеет пользователями, организациями, аутентификацией, расходами, правилами прибыли, ценовыми рекомендациями и веб-скрейпингом. `organization_id` поступает из Account Service без внешнего ключа между базами. Collector никогда не обращается к базе Monitoring. Pricing не дублирует каталог Monitoring как собственные бизнес-сущности.

## Реализованная модель данных

Первая миграция Alembic создаёт восемь бизнес- и инфраструктурных таблиц:

```text
products
competitor_offers
import_jobs
collection_batches
collection_jobs
price_observations
rabbitmq_inbox_events
rabbitmq_outbox_events
```

Основные инварианты:

- связь `Product 1 -> N CompetitorOffer` защищена tenant-safe составным внешним ключом;
- нормализованный URL предложения уникален в рамках организации и товара;
- для товара одновременно может существовать только один batch со статусом `pending` или `processing`;
- collection job обязан ссылаться на batch и offer одного товара;
- один collection job создаёт не более одного price observation;
- observation, связанный с job, обязан ссылаться на competitor offer этого job;
- предложения отключаются через `is_active`, а не удаляются физически;
- каждая успешная проверка создаёт observation, даже если цена не изменилась.

`products.competitor_prices_version` версионирует полный конкурентный снимок товара и начинается с `0`. `competitor_offers.current_price_version` версионирует текущую цену предложения и начинается с `1`. Если цена не изменилась, несколько observations могут иметь одну версию цены.

## Сбор данных и обмен сообщениями

Monitoring публикует через Outbox:

```text
Monitoring -> RabbitMQ -> Collector: collection.requested
```

Collector возвращает:

```text
Collector -> RabbitMQ -> Monitoring: collection.completed
```

Collector получает технические данные задания и не обращается к базе Monitoring. Monitoring определяет контекст через `import_jobs` или `collection_jobs`. Первичный ключ Inbox защищает от повторной обработки события, но создание Inbox-записи и бизнес-изменение должны выполняться в одной транзакции.

При изменении полного конкурентного снимка Monitoring публикует:

```text
Monitoring -> RabbitMQ -> Pricing: product.competitor_prices_updated
```

Событие содержит `organization_id`, `product_id` и `prices_version`. После него Pricing получает по HTTP полный актуальный снимок. RabbitMQ handlers и HTTP endpoints пока не реализованы.

## Структура проекта

```text
src/monitoring_service/
├── api/             # FastAPI routers, dependencies, DTO и handlers
├── contracts/       # HTTP- и messaging-контракты
├── db/
│   ├── models/      # Модели SQLAlchemy
│   ├── repositories/# Реализации запросов к данным
│   └── session.py   # Async engine и фабрика сессий
├── entrypoints/     # Consumers, schedulers и запуск приложения
└── services/        # Бизнес-сценарии и управление транзакциями

alembic/             # Версионированные миграции PostgreSQL
tests/               # Unit-, integration- и API-тесты
```

## Локальная база данных

Один раз создайте локальную конфигурацию:

```powershell
Copy-Item .env.example .env
```

Из каталога `deploy/` запустите PostgreSQL и примените миграции:

```powershell
docker compose up -d monitoring-db
docker compose run --rm monitoring-migrate
```

Для хост-системы PostgreSQL доступен по адресу `localhost:5434`. Контейнеры используют `monitoring-db:5432`. Имя базы и учётные данные берутся из `monitoring-service/.env`; реальный файл нельзя добавлять в Git.

Полезные проверки:

```powershell
docker compose ps monitoring-db
docker compose exec monitoring-db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Из каталога `monitoring-service/` Alembic можно запускать напрямую, используя подключение к хосту из `.env`:

```powershell
uv run alembic current
uv run alembic check
uv run alembic upgrade head
```

## Текущий этап

Реализованы модели SQLAlchemy, конфигурация async-сессий, PostgreSQL в Docker и первая миграция Alembic. Следующие этапы: FastAPI routes, repositories, services, RabbitMQ-контракты и handlers, а также тесты ограничений и конкурентных сценариев.
