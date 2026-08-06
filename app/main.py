from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.storage import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.open_database()  # startup: init schema + open connection, set _connection
    try:
        yield
    except Exception as error:
        raise error
    finally:  # <-- server serves requests here
        await db.close_database()  # shutdown: close connection, set _connection = None


def create_app() -> FastAPI:
    app = FastAPI(title="RAG Document Query Engine", lifespan=lifespan)
    app.include_router(health_router)
    return app


app = create_app()
