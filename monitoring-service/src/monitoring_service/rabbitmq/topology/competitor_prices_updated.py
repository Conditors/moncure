"""
Руслан
перенести к себе весь код этого файла
код обьявляет обменник, очередь и биндит очередь с обменником
их dlx dlq (для мертвых сообщений)
и ретрай обменник и очереди 
"""

from aio_pika.abc import (
    AbstractChannel, 
    AbstractExchange, 
    AbstractQueue, 
    ExchangeType
)

PRICES_UPDATE_EXCHANGE = "prices.update.commands"
PRICING_COMPETITOR_PRICES_UPDATED_QUEUE = "pricing.competitor_prices_updated"
COMPETITOR_PRICES_UPDATED_ROUTING_KEY = "product.competitor_prices_updated"


async def declare_prices_update_exchange(channel: AbstractChannel) -> AbstractExchange:
    return await channel.declare_exchange(PRICES_UPDATE_EXCHANGE, ExchangeType.DIRECT, durable=True, timeout=5)

async def declare_prices_update_queue(channel: AbstractChannel) -> AbstractQueue:
    return await channel.declare_queue(PRICING_COMPETITOR_PRICES_UPDATED_QUEUE, durable=True)

async def bind_prices_update_queue(exchange: AbstractExchange, queue: AbstractQueue) -> None:
    await queue.bind(exchange, routing_key=COMPETITOR_PRICES_UPDATED_ROUTING_KEY)

#TODO добавить dlx dlq ретрай обменник ретрай очередь