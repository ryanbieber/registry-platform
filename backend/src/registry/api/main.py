from fastapi import FastAPI

from registry.api.routes import addresses, health, ingest, registrants, spatial, sources

app = FastAPI(title="RegistryRadar API", version="0.1.0")

app.include_router(health.router)
app.include_router(addresses.router)
app.include_router(registrants.router)
app.include_router(sources.router)
app.include_router(spatial.router)
app.include_router(ingest.router)
