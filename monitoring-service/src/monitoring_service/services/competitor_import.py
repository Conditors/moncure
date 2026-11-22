from collections.abc import Callable
from uuid import UUID

from monitoring_service.contracts.collection import CollectionRequestedPayloadV1
from monitoring_service.db.models.import_job import ImportJob
from monitoring_service.db.models.rabbitmq_outbox import RabbitMqOutbox
from monitoring_service.db.uow import UnitOfWork
from monitoring_service.exceptions.domain_exceptions import (
    CompetitorUrlAlreadyExists,
    ProductNotFoundError,
)
from monitoring_service.services.import_dto import ImportJobResult
from monitoring_service.url_normalization import normalize_product_url


class CompetitorImportService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def start_competitor_import(
        self,
        organization_id: UUID,
        target_product_id: UUID,
        url: str,
    ) -> ImportJobResult:
        normalized_url = normalize_product_url(url)

        async with self._uow_factory() as work:
            target_product = await work.products.get_by_id(
                organization_id=organization_id, product_id=target_product_id
            )
            if target_product is None:
                raise ProductNotFoundError(target_product_id)

            await work.advisory_lock.acquire_competitor_offer_url(
                organization_id=organization_id,
                target_product_id=target_product_id,
                normalized_url=normalized_url,
            )

            competitor = await work.competitors.get_by_normalized_url(
                organization_id=organization_id,
                product_id=target_product_id,
                normalized_url=normalized_url,
            )

            if competitor is not None:
                raise CompetitorUrlAlreadyExists(competitor.id)

            candidate = ImportJob(
                organization_id=organization_id,
                target_product_id=target_product_id,
                url=url,
                normalized_url=normalized_url,
            )

            created_job = await work.import_jobs.create_competitor_if_absent(candidate)

            if created_job is None:
                active_job = await work.import_jobs.get_active_competitor_by_url(
                    organization_id=organization_id,
                    target_product_id=target_product_id,
                    normalized_url=normalized_url,
                )
                if active_job is not None:
                    return ImportJobResult(
                        job_id=active_job.id, status=active_job.status
                    )

                created_job = await work.import_jobs.create_competitor_if_absent(
                    candidate
                )
                if created_job is None:
                    raise RuntimeError("Could not create or find an active import job")

            payload = CollectionRequestedPayloadV1(
                job_id=created_job.id,
                job_kind="IMPORT_JOB",
                url=created_job.normalized_url,
            )

            work.outbox.add(
                RabbitMqOutbox(
                    aggregate_type="import_job",
                    aggregate_id=created_job.id,
                    event_type="collection.requested",
                    schema_version=1,
                    payload=payload.model_dump(mode="json"),
                )
            )

            result = ImportJobResult(job_id=created_job.id, status=created_job.status)
            await work.commit()
            return result
