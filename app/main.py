from fastapi import FastAPI
from app.core.logger import get_logger
from app.api.routes import router
from app.config.settings import settings, validate_settings
import time
import uuid
from app.monitoring.alert_scheduler import (
    start_alert_scheduler,
    stop_alert_scheduler
)
from fastapi import Request

from app.core.request_context import (
    set_request_id,
    reset_request_id,
    get_request_id
)
from app.core.observability import (
    initialize_observability_db,
    migrate_cost_columns
)

logger = get_logger(__name__)

validate_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="A modular LLMOps platform using LangChain and Groq"
)
@app.on_event("startup")
def start_background_monitoring():
    initialize_observability_db()
    migrate_cost_columns()
    start_alert_scheduler()


@app.on_event("shutdown")
def stop_background_monitoring():

    stop_alert_scheduler()



@app.middleware("http")
async def observability_middleware(request: Request, call_next):

    request_id = str(uuid.uuid4())
    token = set_request_id(request_id)

    start_time = time.perf_counter()

    try:
        response = await call_next(request)

        latency = round(
            time.perf_counter() - start_time, 3
        )

        response.headers["X-Request-ID"] = request_id

        logger.info(
            "HTTP request completed",
            extra={"request_id": request_id}
        )

        logger.info(
            f"{request.method} {request.url.path} "
            f"status={response.status_code} "
            f"latency={latency}s",
            extra={"request_id": request_id}
        )

        return response

    except Exception:
        logger.exception(
            "HTTP request failed",
            extra={"request_id": request_id}
        )
        raise

    finally:
        reset_request_id(token)

app.include_router(router)


@app.get("/health")
def health():

    return {
        "status": "healthy",
        "application": settings.APP_NAME,
        "environment": settings.APP_ENV
    }
