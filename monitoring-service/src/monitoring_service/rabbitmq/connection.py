from aio_pika import connect_robust
from aio_pika.abc import AbstractRobustConnection, AbstractChannel

from monitoring_service.config import get_settings

settings = get_settings()

async def connect_rabbitmq() -> AbstractRobustConnection:
    return await connect_robust(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        login=settings.rabbitmq_user,
        password=settings.rabbitmq_password.get_secret_value(),
        virtualhost=settings.rabbitmq_vhost,
        timeout=10
    )

async def declare_channel(connection: AbstractRobustConnection) -> AbstractChannel:
    return await connection.channel(publisher_confirms=True, on_return_raises=True)