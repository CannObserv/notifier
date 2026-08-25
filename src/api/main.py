"""FastAPI application entry point."""

from fastapi import APIRouter, Depends, FastAPI

from src.api.deps import require_api_key
from src.api.routes.apprise_plugins import router as apprise_router
from src.api.routes.channels import router as channels_router
from src.api.routes.dispatch import router as dispatch_router
from src.api.routes.health import router as health_router
from src.api.routes.preview import router as preview_router
from src.api.routes.templates import router as templates_router
from src.api.schemas.errors import AuthErrorDetail
from src.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


app = FastAPI(title="notifier", version="0.1.0")

# Every /api/v1 route inherits require_api_key, so every one of them can fail
# these two ways. Declaring them here puts both in the OpenAPI spec, which is
# what clients/python is generated from — a failure mode absent from the spec
# gives SDK consumers no typed handle on it (issue #22).
# Each carries a model, not just a description: an undescribed response makes
# the SDK generator widen every operation's return type to ``Any``, disabling
# type checking on the success path too.
AUTH_RESPONSES: dict[int | str, dict[str, object]] = {
    401: {"model": AuthErrorDetail, "description": "Invalid API key"},
    403: {
        "model": AuthErrorDetail,
        "description": (
            "No API key supplied, or a key marked 'development' was presented "
            "to a production deployment"
        ),
    },
}

v1_router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_api_key)],
    responses=AUTH_RESPONSES,
)
v1_router.include_router(templates_router)
v1_router.include_router(channels_router)
v1_router.include_router(dispatch_router)
v1_router.include_router(preview_router)
v1_router.include_router(apprise_router)

app.include_router(v1_router)
app.include_router(health_router)
