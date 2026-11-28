""" 
Руслан перенести к себе создание обменника prices_exchange
создание очереди prices_update_queue 
и bind очереди с обменником bind_prices_update_queue
в inbox-воркера примерный путь
src/pricing_service/entrypoints/consumer.py
имена обменника очереди и routing_key в src/monitoring_service/rabbitq/topology/competitor_prices_update.py

Eлисей перенести к себе создание обменника colecctions_exchange
создание очереди collections_requested_queue 
и bind очереди с обменником bind_collection_requested
в inbox-воркера 
src/collector_service/entrypoints/consumer.py
имена обменника очереди и routing_key в src/monitoring_service/rabbitq/topology/collections.py


остальная логика в зависимости от контекста ваших сервисов
после переносов удалить в этом файле создание очередей
"""
import asyncio
import logging

from monitoring_service.config import get_settings
from monitoring_service.db.uow import UnitOfWork
from monitoring_service.rabbitmq.connection import connect_rabbitmq, declare_channel
from monitoring_service.rabbitmq.topology.collections import (
    declare_collections_exchange,
    declare_collection_requested_queue,
    bind_collection_requested,
    COLLECTION_REQUESTED_ROUTING_KEY,
)
from monitoring_service.rabbitmq.topology.competitor_prices_updated import (
    declare_prices_update_exchange, 
    declare_prices_update_queue,
    bind_prices_update_queue,
    COMPETITOR_PRICES_UPDATED_ROUTING_KEY,
)
from monitoring_service.workers.rabbitmq_outbox import RabbitMqOutboxWorker
from monitoring_service.db.session import async_session_factory, async_engine

logger = logging.getLogger(__name__)

settings = get_settings()

def create_uow() -> UnitOfWork:
    return UnitOfWork(async_session_factory)

async def main() -> None:
    connection = await connect_rabbitmq()

    try:
        channel = await declare_channel(connection)

        collection_exchange = await declare_collections_exchange(channel)
        prices_exchange = await declare_prices_update_exchange(channel)

        logger.info("publisher started")

        exchanges_by_event_type = {
            COLLECTION_REQUESTED_ROUTING_KEY: collection_exchange,
            COMPETITOR_PRICES_UPDATED_ROUTING_KEY: prices_exchange,
        }

        collection_requested_queue = await declare_collection_requested_queue(channel)
        await bind_collection_requested(collection_exchange, collection_requested_queue)

        prices_update_queue = await declare_prices_update_queue(channel)
        await bind_prices_update_queue(prices_exchange, prices_update_queue)

        worker = RabbitMqOutboxWorker(
            uow_factory=create_uow,
            batch_size=settings.outbox_batch_size,
            outbox_poll_interval_seconds=settings.outbox_poll_interval_seconds,
            exchanges_by_event_type=exchanges_by_event_type,
        )

        await worker.run()


    finally:
        await connection.close()
        await async_engine.dispose()
        logger.info("publisher stopped")



if __name__ == "__main__":
    asyncio.run(main())