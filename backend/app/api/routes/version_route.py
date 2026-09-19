"""Version endpoint for TacticX release verification."""
from __future__ import annotations

from fastapi import APIRouter

from app.version import get_version_info

router = APIRouter(tags=["system"])


@router.get("/version")
def version_endpoint() -> dict:
    """Return non-sensitive version and build metadata."""
    return get_version_info()
