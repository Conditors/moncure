import asyncio
from datetime import datetime, UTC

from aio_pika.exceptions import AMQPError
from aio_pika.abc import AbstractExchange
from collections.abc import Callable, Mapping

from monitoring_service.contracts.collection import CollectionRequestedPayloadV1, CollectionRequestedV1
from monitoring_service.contracts.competitor_prices import CompetitorPricesUpdatedPayloadV1, CompetitorPricesUpdatedV1
from monitoring_service.db.models.rabbitmq_outbox import RabbitMqOutbox
from monitoring_service.db.uow import UnitOfWork
from monitoring_service.rabbitmq.publisher import publish_message



class RabbitMqOutoxPublisher:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        exchanges_by_event_type: Mapping[str, AbstractExchange],
        batch_size: int,
    ):
        self._uow_factory = uow_factory
        self._exchanges_by_event_type = exchanges_by_event_type
        self._batch_size = batch_size
        

        if batch_size <= 0:
            raise ValueError("batch_size must be positive")


    def _serialize_event(self, event: RabbitMqOutbox):
        envelope: CollectionRequestedV1 | CompetitorPricesUpdatedV1
        match event.event_type:
            case "collection.requested":
                collection_payload = CollectionRequestedPayloadV1.model_validate(event.payload)
                envelope = CollectionRequestedV1(
                    message_id=event.event_id,
                    contract_version=event.schema_version,
                    job_id=collection_payload.job_id,
                    job_kind=collection_payload.job_kind,
                    url=collection_payload.url,
                    requested_at=event.occurred_at
                )

            case "product.competitor_prices_updated":
                pricing_payload = CompetitorPricesUpdatedPayloadV1.model_validate(event.payload)
                envelope = CompetitorPricesUpdatedV1(
                    message_id=event.event_id,
                    contract_version=event.schema_version,
                    organization_id=pricing_payload.organization_id,
                    product_id=pricing_payload.product_id,
                    prices_version=pricing_payload.prices_version,
                    occurred_at=event.occurred_at,
                )

            case unsupported_event_type:
                raise ValueError(f"Unsupported RabbitMQ outbox event type: {unsupported_event_type}")

        return envelope.model_dump_json().encode("utf-8")


    async def publish_batch(self) -> int:
        async with self._uow_factory() as work:
            events = await work.outbox.get_unpublished_batch(self._batch_size)
            published_count = 0
            for event in events:
                body = self._serialize_event(event)

                exchange = self._exchanges_by_event_type.get(event.event_type)
                if exchange is None:
                    raise ValueError(
                        f"No RabbitMQ exchange configured for event type: {event.event_type}"
                    )
                try:    
                    await publish_message(
                        exchange=exchange,
                        routing_key=event.event_type,
                        body=body,
                        message_id=str(event.event_id),
                        correlation_id=str(event.aggregate_id),
                    )
                except (OSError, AMQPError):
                    await work.commit()
                    raise

                await work.outbox.mark_published(event, datetime.now(UTC))
                published_count += 1
            await work.commit()

        return published_count

class RabbitMqOutboxWorker:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        batch_size: int,
        outbox_poll_interval_seconds: float,
        exchanges_by_event_type: Mapping[str, AbstractExchange],
    ):
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if outbox_poll_interval_seconds <= 0:
            raise ValueError("outbox_poll_interval_seconds must be positive")

        self._uow_factory = uow_factory
        self._batch_size = batch_size
        self._outbox_poll_interval_seconds = outbox_poll_interval_seconds
        self._exchanges_by_event_type = dict(exchanges_by_event_type)

    async def run(self) -> None:
        publisher = RabbitMqOutoxPublisher(
            uow_factory=self._uow_factory,
            exchanges_by_event_type=self._exchanges_by_event_type,
            batch_size=self._batch_size
        )
        while True:
            try:
                published_count = await publisher.publish_batch()

            except (OSError, AMQPError):
                await asyncio.sleep(self._outbox_poll_interval_seconds)
                continue

            if published_count == 0:
                await asyncio.sleep(self._outbox_poll_interval_seconds)