# src/routes/agent/__init__.py
"""Agent Routes Package"""
from fastapi import APIRouter

from . import query
from . import webhook
from . import queue
from . import status
from . import logs

# Create main agent router with /agent prefix
router = APIRouter(prefix="/agent", tags=["agent"])

# Include sub-routers (they have no prefix, query module has /ask, /batch-email, etc.)
router.include_router(query.router)      # /agent/ask, /agent/batch-email, etc.
# router.include_router(webhook.router)    # /agent/webhook/...
router.include_router(queue.router)      # /agent/queue/...
router.include_router(status.router)     # /agent/status/...
router.include_router(logs.router)       # /agent/logs/...

__all__ = ["router"]