"""Celery tasks for background batch validation."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.connection import ConnectionProfile
from app.models.mapping import MigrationProject, ObjectMapping
from app.models.validation import ValidationRun
from app.services.validation_engine import run_validation_for_object
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_async_session() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(settings.DATABASE_URL)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _run_validation_async(validation_run_id: str):
    """Execute validation run asynchronously."""
    session_factory = _get_async_session()

    async with session_factory() as db:
        run = await db.get(ValidationRun, validation_run_id)
        if not run:
            logger.error(f"ValidationRun {validation_run_id} not found")
            return

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            project = await db.get(MigrationProject, run.project_id)
            source_profile = await db.get(ConnectionProfile, project.source_connection_id)
            target_profile = await db.get(ConnectionProfile, project.target_connection_id)

            # Get object mappings to validate
            if run.object_mapping_ids:
                mappings_result = await db.execute(
                    select(ObjectMapping).where(
                        ObjectMapping.id.in_(run.object_mapping_ids),
                        ObjectMapping.is_active == True,
                    )
                )
            else:
                mappings_result = await db.execute(
                    select(ObjectMapping).where(
                        ObjectMapping.project_id == run.project_id,
                        ObjectMapping.is_active == True,
                    )
                )
            object_mappings = list(mappings_result.scalars().all())

            for om in object_mappings:
                await run_validation_for_object(db, run, om, source_profile, target_profile)

            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()

        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.error(f"Validation run {validation_run_id} failed: {e}")


@celery_app.task(name="run_batch_validation", bind=True, max_retries=1)
def run_batch_validation(self, validation_run_id: str):
    """Celery task wrapper for batch validation."""
    try:
        asyncio.run(_run_validation_async(validation_run_id))
    except Exception as exc:
        logger.error(f"Batch validation task failed: {exc}")
        raise self.retry(exc=exc, countdown=60)
