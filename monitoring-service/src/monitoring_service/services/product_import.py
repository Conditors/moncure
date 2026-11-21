from collections.abc import Callable
from uuid import UUID
from dataclasses import dataclass

from monitoring_service.contracts.collection import CollectionCompletedV1, CollectionRequestedPayloadV1, ImportDraftV1
from monitoring_service.db.models.import_job import ImportJob, ImportJobStatus
from monitoring_service.db.models.rabbitmq_outbox import RabbitMqOutbox
from monitoring_service.db.uow import UnitOfWork
from monitoring_service.exceptions.domain_exceptions import ImportJobNotFoundError, ProductUrlAlreadyExists
from monitoring_service.url_normalization import normalize_product_url

@dataclass(frozen=True)
class ImportJobResult:
    job_id: UUID
    status: ImportJobStatus


class ProductImportService:

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory


    async def start_own_product(
        self, 
        organization_id: UUID,
        url: str
    ) -> ImportJobResult:
        normalized_url = normalize_product_url(url)

        async with self._uow_factory() as work:
            await work.advisory_lock.acquire_product_url(organization_id, normalized_url)

            product = await work.products.get_by_normalized_url(organization_id, normalized_url)
            if product is not None:
                raise ProductUrlAlreadyExists(product.id)


            candidate = ImportJob(
                organization_id=organization_id,
                url=url,
                normalized_url=normalized_url,
            )

            created_job = await work.import_jobs.create_own_if_absent(candidate)

            if created_job is None:
                active_job = await work.import_jobs.get_active_own_by_url(
                    organization_id, normalized_url
                )
                if active_job is not None:
                    return ImportJobResult(job_id=active_job.id, status=active_job.status)

                created_job = await work.import_jobs.create_own_if_absent(candidate)
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

    async def apply_collection_result(self, event: CollectionCompletedV1) -> bool:

        if event.job_kind != "IMPORT_JOB":
            raise ValueError("Expected IMPORT_JOB result")

        async with self._uow_factory() as work:
            is_new = await work.inbox.try_add(
                event_id=event.message_id, 
                event_type="collection.completed"
            )

            if not is_new:
                return False

            existed_job = await work.import_jobs.get_by_id_for_update(event.job_id)
            if existed_job is None:
                raise ImportJobNotFoundError(event.job_id)

            if existed_job.status != ImportJobStatus.PENDING:
                await work.commit()
                return False

            if event.status == "FAILED":
                existed_job.error_code = event.error.code
                existed_job.error_message = event.error.message
                existed_job.status = ImportJobStatus.FAILED

            elif event.data.availability_status != "AVAILABLE":
                existed_job.error_code = "product_unavailable"
                existed_job.status = ImportJobStatus.FAILED

            else:
                draft_data = ImportDraftV1(
                    name=event.data.name,
                    price=event.data.price,
                    currency=event.data.currency,
                    article=event.data.article,
                    source=event.data.source,
                )
                existed_job.status = ImportJobStatus.READY_FOR_REVIEW
                existed_job.draft_data = draft_data.model_dump(mode="json")
                existed_job.result_observed_at = event.completed_at

            await work.commit()
            return True

