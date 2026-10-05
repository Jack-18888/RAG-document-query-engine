"""Liveness endpoint used to check the server is up."""

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a simple ``{"status": "ok"}`` heartbeat."""
    return {"status": "ok"}
