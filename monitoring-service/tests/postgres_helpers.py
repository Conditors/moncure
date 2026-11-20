import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def backend_pid(session: AsyncSession) -> int:
    return (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()


async def wait_for_blocker(
    observer: AsyncSession,
    blocker_pid: int,
    waiter_pid: int,
) -> None:
    assert blocker_pid != waiter_pid
    statement = text("SELECT :blocker = ANY(pg_blocking_pids(:waiter))")
    async with asyncio.timeout(5):
        while not await observer.scalar(
            statement, {"blocker": blocker_pid, "waiter": waiter_pid}
        ):
            await asyncio.sleep(0.01)
