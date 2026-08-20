from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import assessments, dashboard, findings, imports, owners, remediations, validations

settings = get_settings()

app = FastAPI(
    title="AD Security Remediation Tracker API",
    description="Ingests AD security assessment findings (Pentera first) and "
    "tracks remediation and validation through to measurable risk reduction.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assessments.router)
app.include_router(findings.router)
app.include_router(remediations.router)
app.include_router(validations.router)
app.include_router(dashboard.router)
app.include_router(imports.router)
app.include_router(owners.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
