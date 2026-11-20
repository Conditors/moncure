from hashlib import blake2b
from uuid import UUID

from sqlalchemy import BigInteger, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession


class PostgresAdvisoryLock:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def acquire_product_url(
        self,
        organization_id: UUID,
        normalized_url: str,
    ) -> None:
        key_bytes = (
            b"monitoring:own-product-url:v1\x00"
            + organization_id.bytes
            + normalized_url.encode("utf-8")
        )

        digest = blake2b(key_bytes, digest_size=8).digest()
        lock_key = int.from_bytes(digest, byteorder="big", signed=True)

        statement = text(
            "SELECT pg_advisory_xact_lock(:lock_key)"
        ).bindparams(bindparam("lock_key", type_=BigInteger()))

        await self._session.execute(statement, {"lock_key": lock_key})
