from fastapi import FastAPI
from app.api.endpoints import setup, webhooks, calls
from app.database import create_db_and_tables # <-- Import this
import json
from starlette.requests import Request

def on_startup():
    create_db_and_tables()

app = FastAPI(
    title="Orani AI Assistant API",
    on_startup=[on_startup],
    description="API for managing and interacting with the Orani AI phone assistant.",
    version="1.0.0"
)
@app.middleware("http")
async def log_request_body(request: Request, call_next):
    """
    This middleware intercepts all incoming requests.
    If the request is a POST to /setup/assistant, it prints the raw body.
    """
    if request.method == "POST" and request.url.path == "/setup/assistant":
        body_bytes = await request.body()
        
        print("\n" + "="*50)
        print("🕵️‍ RAW JSON BODY FOR /setup/assistant 🕵️‍")
        print("="*50)
        try:
            body_json = json.loads(body_bytes)
            print(json.dumps(body_json, indent=2))
        except json.JSONDecodeError:
            print(body_bytes.decode(errors='ignore'))
        print("="*50 + "\n")

        async def receive():
            return {"type": "http.request", "body": body_bytes}
        
        request = Request(request.scope, receive)

    response = await call_next(request)
    return response

app.include_router(setup.router, prefix="/setup", tags=["Setup"])
app.include_router(webhooks.router, prefix="/webhook", tags=["Webhooks"])
app.include_router(calls.router, prefix="/call", tags=["Calls"])

@app.get("/", tags=["Root"])
def read_root():
    """A simple health check endpoint."""
    return {"status": "Orani AI Assistant API is running"}