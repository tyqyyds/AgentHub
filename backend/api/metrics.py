from fastapi import APIRouter, Response
from backend.integrations.prometheus_exporter import get_prometheus_exporter
from backend.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/metrics")
async def metrics():
    if not settings.prometheus_enabled:
        return Response(content="", media_type="text/plain", status_code=404)
    exporter = get_prometheus_exporter()
    content = exporter.generate_metrics()
    return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")
