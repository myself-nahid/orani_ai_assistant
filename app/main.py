from fastapi import FastAPI
from app.api.endpoints import setup, webhooks, calls

# FastAPI app instance
app = FastAPI(
    title="Orani AI Assistant API",
    description="API for managing and interacting with the Orani AI phone assistant.",
    version="1.0.0"
)

# API routers
app.include_router(setup.router, prefix="/setup", tags=["Setup"])
app.include_router(webhooks.router, prefix="/webhook", tags=["Webhooks"])
app.include_router(calls.router, prefix="/call", tags=["Calls"])

@app.get("/", tags=["Root"])
def read_root():
    """A simple health check endpoint."""
    return {"status": "Orani AI Assistant API is running"}