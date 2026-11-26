from aio_pika import Message, DeliveryMode
from aio_pika.abc import AbstractExchange, HeadersType


async def publish_message(
    exchange: AbstractExchange,
    routing_key: str,
    body: bytes,
    message_id: str,
    correlation_id: str,
    headers: HeadersType
) -> None:
    message = Message(
        body=body,
        headers=headers,
        content_type="application/json",
        content_encoding="utf-8",
        delivery_mode=DeliveryMode.PERSISTENT,
        correlation_id=correlation_id,
        message_id=message_id,
    )

    await exchange.publish(message, routing_key, mandatory=True, timeout=5)