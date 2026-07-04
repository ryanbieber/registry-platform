from fastapi import FastAPI

from registry.api.routes import health, ingest, registrants, sources

app = FastAPI(title="Registry Platform API", version="0.1.0")

app.include_router(health.router)
app.include_router(registrants.router)
app.include_router(sources.router)
app.include_router(ingest.router)
