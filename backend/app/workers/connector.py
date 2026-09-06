import asyncio
import logging
import socket
from dataclasses import dataclass, replace
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.schemas import DocumentCapture
from app.core.config import Settings, get_settings
from app.core.database import SessionFactory, create_database
from app.core.models import ConnectorJob, ConnectorJobStatus
from app.services.connector_jobs import claim_connector_job, finish_connector_job
from app.services.storage import SourceMetadataConflict, capture_document, get_run
from app.services.web_connector import PublicWebConnector, WebConnectorOutcome
from app.services.web_connector_factory import create_public_web_connector

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ConnectorWorker:
    session_factory: SessionFactory
    connector: PublicWebConnector
    worker_id: str
    lease_seconds: int = 300
    poll_seconds: float = 1.0

    async def run_once(self) -> bool:
        async with self.session_factory() as session:
            job = await claim_connector_job(session, self.worker_id, self.lease_seconds)
        if job is None:
            return False
        logger.info(
            "connector_job_claimed",
            extra={"job_id": str(job.id), "claim_count": job.claim_count},
        )
        await self._execute(job)
        return True

    async def run_forever(self, stop: asyncio.Event | None = None) -> None:
        stop_event = stop or asyncio.Event()
        while not stop_event.is_set():
            worked = await self.run_once()
            if worked:
                continue
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.poll_seconds)
            except TimeoutError:
                pass

    async def _execute(self, job: ConnectorJob) -> None:
        if job.publisher is None or job.source_type is None or job.request_hash is None:
            outcome = WebConnectorOutcome(
                status=ConnectorJobStatus.UNAVAILABLE,
                requested_url=job.requested_url,
                attempts=0,
                error_code="legacy_job_payload_unavailable",
                error_message="This pre-worker job does not contain a recoverable request payload.",
            )
        else:
            try:
                outcome = await self.connector.collect(job.requested_url)
            except Exception:
                logger.exception("connector_job_unhandled_failure", extra={"job_id": str(job.id)})
                outcome = WebConnectorOutcome(
                    status=ConnectorJobStatus.UNAVAILABLE,
                    requested_url=job.requested_url,
                    attempts=0,
                    error_code="worker_unhandled_error",
                    error_message="Connector execution failed unexpectedly.",
                )

        document_id = None
        async with self.session_factory() as session:
            if outcome.status == ConnectorJobStatus.SUCCEEDED:
                assert outcome.final_url is not None
                assert outcome.text is not None
                run = await get_run(session, job.run_id)
                if run is None:
                    outcome = replace(
                        outcome,
                        status=ConnectorJobStatus.UNAVAILABLE,
                        error_code="run_unavailable",
                        error_message="The analysis run no longer exists.",
                    )
                else:
                    try:
                        _, document, _, _ = await capture_document(
                            session,
                            run,
                            DocumentCapture(
                                url=outcome.final_url,
                                publisher=job.publisher,
                                publisher_family=job.publisher_family,
                                source_type=job.source_type,
                                title=job.title or outcome.title,
                                raw_content=outcome.text,
                                published_at=job.published_at,
                            ),
                        )
                    except SourceMetadataConflict:
                        outcome = replace(
                            outcome,
                            status=ConnectorJobStatus.UNAVAILABLE,
                            error_code="source_metadata_conflict",
                            error_message=(
                                "Source metadata conflicts with an existing source record."
                            ),
                        )
                    else:
                        document_id = document.id

            finished = await finish_connector_job(
                session, job.id, self.worker_id, outcome, document_id
            )
        if not finished:
            logger.warning("connector_job_lease_lost", extra={"job_id": str(job.id)})
            return
        logger.info(
            "connector_job_finished",
            extra={"job_id": str(job.id), "status": outcome.status.value},
        )


def build_worker(settings: Settings | None = None) -> tuple[ConnectorWorker, AsyncEngine]:
    resolved = settings or get_settings()
    engine, session_factory = create_database(resolved.database_url)
    worker_id = f"{socket.gethostname()}-{uuid4().hex[:12]}"
    return (
        ConnectorWorker(
            session_factory=session_factory,
            connector=create_public_web_connector(resolved),
            worker_id=worker_id,
            lease_seconds=resolved.connector_worker_lease_seconds,
            poll_seconds=resolved.connector_worker_poll_seconds,
        ),
        engine,
    )


async def async_main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    worker, engine = build_worker(settings)
    try:
        await worker.run_forever()
    finally:
        await engine.dispose()


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
