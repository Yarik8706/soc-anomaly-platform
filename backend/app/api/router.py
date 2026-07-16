from fastapi import APIRouter

from app.api.anomalies import router as anomalies_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.reports import router as reports_router
from app.api.runs import router as runs_router
from app.api.uploads import router as uploads_router
from app.api.users import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(runs_router)
api_router.include_router(auth_router)
api_router.include_router(uploads_router)
api_router.include_router(anomalies_router)
api_router.include_router(reports_router)
api_router.include_router(metrics_router)
api_router.include_router(users_router)
api_router.include_router(audit_router)
