from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from monitoring_service.db.models.import_job import (
    ImportJob,
    ImportJobStatus,
    ImportJobType,
)


class ImportJobRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id_for_organization(
        self,
        organization_id: UUID,
        job_id: UUID,
    ) -> ImportJob | None:
        statement = (
            select(ImportJob)
            .where(
                (ImportJob.id == job_id),
                (ImportJob.organization_id == organization_id), 
            )
        )
        job = await self._session.execute(statement)
        return job.scalar_one_or_none()
    
    async def get_by_id_for_update_for_organization(
        self,
        organization_id: UUID,
        job_id: UUID,
    ) -> ImportJob | None:
        statement = (
            select(ImportJob)
            .with_for_update()
            .execution_options(populate_existing=True)
            .where(
                (ImportJob.id == job_id),
                (ImportJob.organization_id == organization_id), 
            )
        )
        job = await self._session.execute(statement)
        return job.scalar_one_or_none()

    async def get_by_id_for_update(
        self,
        job_id: UUID,
    ) -> ImportJob | None:
        statement = (
            select(ImportJob).with_for_update()
            .where(ImportJob.id == job_id)
        )
        
        job = await self._session.execute(statement)
        return job.scalar_one_or_none()

    async def get_active_own_by_url(
        self,
        organization_id: UUID,
        normalized_url: str,
    ) -> ImportJob | None:
        statement = (
            select(ImportJob)
            .where(
                (ImportJob.normalized_url == normalized_url),
                (ImportJob.organization_id == organization_id), 
                (ImportJob.job_type == ImportJobType.OWN_PRODUCT_IMPORT),
                (ImportJob.status.in_(
                    (ImportJobStatus.READY_FOR_REVIEW, ImportJobStatus.PENDING, ImportJobStatus.PROCESSING)
                    )
                ),
            )
        )
        job = await self._session.execute(statement)
        return job.scalar_one_or_none()

    async def get_active_competitor_by_url(
        self,
        organization_id: UUID,
        target_product_id: UUID,
        normalized_url: str,
    ) -> ImportJob | None:
        statement = (
            select(ImportJob)
            .where(
                (ImportJob.normalized_url == normalized_url),
                (ImportJob.organization_id == organization_id),
                (ImportJob.target_product_id == target_product_id),
                (ImportJob.job_type == ImportJobType.COMPETITOR_OFFER_IMPORT),
                (ImportJob.status.in_(
                    (ImportJobStatus.READY_FOR_REVIEW, ImportJobStatus.PENDING, ImportJobStatus.PROCESSING)
                    )
                ),
            )
        )
        job = await self._session.execute(statement)
        return job.scalar_one_or_none()

    async def create_own_if_absent(
        self,
        job: ImportJob,
    ) -> ImportJob | None:
        statement = (
            insert(ImportJob)
            .values(
                organization_id=job.organization_id,
                job_type=ImportJobType.OWN_PRODUCT_IMPORT,
                status=ImportJobStatus.PENDING,
                url=job.url,
                normalized_url=job.normalized_url,
            )
        )
        if job.id is not None:
            statement = statement.values(id=job.id)

        returning_statement = (
            statement.on_conflict_do_nothing(
                index_elements=[ImportJob.organization_id, ImportJob.normalized_url],
                index_where=text(
                    "job_type = 'own_product_import' "
                    "AND status IN ('pending', 'processing', 'ready_for_review')"
                )
            )
            .returning(ImportJob)
        )
        result = await self._session.execute(returning_statement)
        return result.scalar_one_or_none()

    async def create_competitor_if_absent(
            self,
            job: ImportJob,
        ) -> ImportJob | None:
            statement = (
                insert(ImportJob)
                .values(
                    organization_id=job.organization_id,
                    target_product_id=job.target_product_id,
                    job_type=ImportJobType.COMPETITOR_OFFER_IMPORT,
                    status=ImportJobStatus.PENDING,
                    url=job.url,
                    normalized_url=job.normalized_url,
                )
            )
            if job.id is not None:
                statement = statement.values(id=job.id)
    
            returning_statement = (
                statement.on_conflict_do_nothing(
                    index_elements=[ImportJob.organization_id, ImportJob.target_product_id, ImportJob.normalized_url],
                    index_where=text(
                        "job_type = 'competitor_offer_import' "
                        "AND status IN ('pending', 'processing', 'ready_for_review')"
                    )
                )
                .returning(ImportJob)
            )
            result = await self._session.execute(returning_statement)
            return result.scalar_one_or_none()
