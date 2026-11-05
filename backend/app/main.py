import logging
from pathlib import Path
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import get_settings
from app.database import SessionLocal
from app.routes.assistant import router as assistant_router
from app.routes.criteria import router as criteria_router
from app.routes.evidence import router as evidence_router
from app.routes.history import router as history_router
from app.routes.human_reviews import router as human_reviews_router
from app.routes.runs import router as runs_router
from app.storage.access import AccessContext, get_access

settings = get_settings()

app = FastAPI(title="LLM Testing Harness API", version="0.1.0")

logger = logging.getLogger("harness.operations")


@app.middleware("http")
async def operational_boundary(request, call_next):
    request_id, started = uuid4().hex, perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # Do not log exception bodies/SQL parameters/provider payloads or JWTs.
        logger.error("request_failed id=%s category=internal_error", request_id)
        response = JSONResponse(
            {"detail": "The request could not be completed.", "request_id": request_id},
            status_code=500,
        )
    route = request.scope.get("route")
    logger.info(
        "request id=%s stage=%s status=%s duration_ms=%d",
        request_id,
        getattr(route, "path", "unmatched"),
        response.status_code,
        round((perf_counter() - started) * 1000),
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin).rstrip("/") for origin in settings.cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(runs_router)
app.include_router(assistant_router, dependencies=[Depends(get_access)])
app.include_router(criteria_router, dependencies=[Depends(get_access)])
app.include_router(human_reviews_router)
app.include_router(history_router)
app.include_router(evidence_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        with SessionLocal() as session:
            revision = session.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != "0006_omar_storage":
            raise ValueError()
        if settings.app_env != "development" and (
            settings.auth_mode != "oidc"
            or not all(
                (
                    settings.oidc_issuer,
                    settings.oidc_audience,
                    settings.oidc_jwks_url,
                    settings.authorized_subjects,
                )
            )
        ):
            raise ValueError()
        return {"status": "ready", "schema": revision}
    except Exception:
        raise HTTPException(503, "Database/schema/auth configuration is not ready.") from None


@app.get("/auth/me")
def me(access: Annotated[AccessContext, Depends(get_access)]):
    return {"subject": access.principal.subject, "project_id": access.project_id}


static = Path(__file__).parent.parent / "static"
if static.is_dir():
    app.mount("/", StaticFiles(directory=static, html=True), name="frontend")
