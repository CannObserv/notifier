"""FastAPI application entry point."""

from fastapi import APIRouter, Depends, FastAPI

from src.api.deps import require_api_key
from src.api.routes.apprise_plugins import router as apprise_router
from src.api.routes.channels import router as channels_router
from src.api.routes.dispatch import router as dispatch_router
from src.api.routes.health import router as health_router
from src.api.routes.preview import router as preview_router
from src.api.routes.templates import router as templates_router
from src.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


app = FastAPI(title="notifier", version="0.1.0")

v1_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])
v1_router.include_router(templates_router)
v1_router.include_router(channels_router)
v1_router.include_router(dispatch_router)
v1_router.include_router(preview_router)
v1_router.include_router(apprise_router)

app.include_router(v1_router)
app.include_router(health_router)
