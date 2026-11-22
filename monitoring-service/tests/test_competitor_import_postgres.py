import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from monitoring_service.db.models import (
    ImportJob,
    ImportJobType,
    Product,
    RabbitMqOutbox,
)
from monitoring_service.db.models.competitor_offer import (
    CompetitorAvailabilityStatus,
    CompetitorOffer,
)
from monitoring_service.db.uow import UnitOfWork
from monitoring_service.exceptions.domain_exceptions import (
    CompetitorUrlAlreadyExists,
    ProductNotFoundError,
)
from monitoring_service.services.competitor_import import CompetitorImportService

pytestmark = pytest.mark.asyncio
URL = "https://example.com/item"


@pytest_asyncio.fixture
async def targets(engine: AsyncEngine) -> tuple[UUID, UUID, UUID]:
    organization_id, product_a, product_b = uuid4(), uuid4(), uuid4()
    async with AsyncSession(engine) as session, session.begin():
        for product_id in (product_a, product_b):
            session.add(
                Product(
                    id=product_id,
                    organization_id=organization_id,
                    name="Target",
                    price=Decimal(10),
                    currency="RUB",
                )
            )
    return organization_id, product_a, product_b


@pytest.mark.parametrize("foreign", [False, True])
async def test_missing_or_foreign_target_creates_no_import(
    engine: AsyncEngine, targets: tuple[UUID, UUID, UUID], foreign: bool
) -> None:
    owner, product_id, _ = targets
    organization_id, target_id = (uuid4(), product_id) if foreign else (owner, uuid4())
    sessions = async_sessionmaker(engine)
    service = CompetitorImportService(lambda: UnitOfWork(sessions))
    url = f"{URL}/{uuid4()}"

    with pytest.raises(ProductNotFoundError) as raised:
        await service.start_competitor_import(organization_id, target_id, url)
    assert raised.value.product_id == target_id
    async with sessions() as reader:
        assert (
            await reader.scalar(select(ImportJob.id).where(ImportJob.url == url))
            is None
        )
        assert (
            await reader.scalar(
                select(RabbitMqOutbox.event_id).where(
                    RabbitMqOutbox.payload["url"].astext == url
                )
            )
            is None
        )


async def test_existing_offer_error_returns_offer_id(
    engine: AsyncEngine, targets: tuple[UUID, UUID, UUID]
) -> None:
    organization_id, product_id, _ = targets
    offer_id = uuid4()
    sessions = async_sessionmaker(engine)
    async with sessions.begin() as session:
        session.add(
            CompetitorOffer(
                id=offer_id,
                organization_id=organization_id,
                product_id=product_id,
                name="Existing offer",
                url=URL,
                normalized_url=URL,
                current_price=Decimal(10),
                currency="RUB",
                availability_status=CompetitorAvailabilityStatus.AVAILABLE,
                last_checked_at=datetime.now(UTC),
            )
        )

    service = CompetitorImportService(lambda: UnitOfWork(sessions))
    with pytest.raises(CompetitorUrlAlreadyExists) as raised:
        await service.start_competitor_import(organization_id, product_id, URL)
    assert raised.value.competitor_offer_id == offer_id


async def test_concurrent_start_deduplicates_only_for_same_target(
    engine: AsyncEngine, targets: tuple[UUID, UUID, UUID]
) -> None:
    organization_id, product_a, product_b = targets
    sessions = async_sessionmaker(engine)
    service = CompetitorImportService(lambda: UnitOfWork(sessions))

    first, duplicate, other = await asyncio.gather(
        service.start_competitor_import(organization_id, product_a, URL),
        service.start_competitor_import(organization_id, product_a, URL),
        service.start_competitor_import(organization_id, product_b, URL),
    )
    assert first == duplicate
    assert first.job_id != other.job_id

    async with sessions() as reader:
        jobs = (
            await reader.scalars(
                select(ImportJob).where(ImportJob.organization_id == organization_id)
            )
        ).all()
        assert {(job.target_product_id, job.job_type) for job in jobs} == {
            (product_a, ImportJobType.COMPETITOR_OFFER_IMPORT),
            (product_b, ImportJobType.COMPETITOR_OFFER_IMPORT),
        }
        assert len(jobs) == 2
        events = (
            await reader.scalars(
                select(RabbitMqOutbox).where(
                    RabbitMqOutbox.aggregate_id.in_([first.job_id, other.job_id])
                )
            )
        ).all()
        assert len(events) == 2
        assert {event.aggregate_id for event in events} == {first.job_id, other.job_id}
        assert all(event.payload["url"] == URL for event in events)
