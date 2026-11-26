from aio_pika.abc import (
    AbstractChannel, 
    AbstractExchange, 
    AbstractQueue, 
    ExchangeType
)

"""
Елисей 
строки с n по m перенести к себе 
код обьявляет обменник, очередь и биндит очередь с обменником
их dlx dlq (для мертвых сообщений)
и ретрай обменник и очереди 
"""

COLLECTION_EXCHANGE = "collections.commands"

COLLECTION_REQUESTED_QUEUE = "collector.collection.requested"
COLLECTION_REQUESTED_ROUTING_KEY = "collection.requested"

async def declare_collections_exchange(channel: AbstractChannel) -> AbstractExchange:
    return await channel.declare_exchange(COLLECTION_EXCHANGE, ExchangeType.DIRECT, durable=True, timeout=5)

async def declare_collection_requested_queue(channel: AbstractChannel) -> AbstractQueue:
    return await channel.declare_queue(COLLECTION_REQUESTED_QUEUE, durable=True)

async def bind_collection_requested(exchange: AbstractExchange, queue: AbstractQueue) -> None:
    await queue.bind(exchange, routing_key=COLLECTION_REQUESTED_ROUTING_KEY)

#TODO добавить dlx dlq ретрай обменник ретрай очередь

COLLECTION_COMPLETED_QUEUE = "monitoring.collection.completed"
COLLECTION_COMPLETED_ROUTING_KEY = "collection.completed"


async def declare_completed_queue(channel: AbstractChannel) -> AbstractQueue:
    return await channel.declare_queue(COLLECTION_COMPLETED_QUEUE, durable=True)

async def bind_completed_queue(exchange: AbstractExchange, queue: AbstractQueue) -> None:
    await queue.bind(exchange, routing_key=COLLECTION_COMPLETED_ROUTING_KEY)

#TODO добавить dlx dlq ретрай обменник ретрай очередь


