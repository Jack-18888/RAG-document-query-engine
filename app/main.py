from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.queries import router as queries_router
from app.config import get_settings
from app.jobs.worker import JobExecutor
from app.storage import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.open_database()  # startup: init schema + open connection, set _connection
    executor = JobExecutor(max_workers=get_settings().job_max_workers)
    app.state.job_executor = executor
    try:
        yield
    except Exception as error:
        raise error
    finally:
        executor.shutdown()
        await db.close_database()


def create_app() -> FastAPI:
    app = FastAPI(title="RAG Document Query Engine", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(documents_router)
    app.include_router(jobs_router)
    app.include_router(queries_router)
    return app


app = create_app()
