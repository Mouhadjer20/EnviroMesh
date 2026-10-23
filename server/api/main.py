"""FastAPI application entry point for the EnviroMesh core server.

Hosts the REST API for devices, telemetry, alerts, and users, plus WebSocket
endpoints for real-time telemetry streaming to the dashboard.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import devices, telemetry, alerts, users

app = FastAPI(
    title="EnviroMesh API",
    description="Core server API for the Environmental Monitoring System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to dashboard origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(devices.router)
app.include_router(telemetry.router)
app.include_router(alerts.router)
app.include_router(users.router)


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}