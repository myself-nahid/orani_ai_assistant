from fastapi import FastAPI
from dotenv import load_dotenv 
load_dotenv()
from app.api.endpoints import setup, webhooks, calls, summaries, notifications, messaging, history
from app.database import create_db_and_tables, manually_add_structured_summary_column
import json
from starlette.requests import Request
from app.firebase_service import initialize_firebase

def on_startup():
    create_db_and_tables()
    manually_add_structured_summary_column()
    initialize_firebase()

app = FastAPI(
    title="Orani AI Assistant API",
    on_startup=[on_startup],
    description="API for managing and interacting with the Orani AI phone assistant.",
    version="1.0.0"
)
@app.middleware("http")
async def log_request_body(request: Request, call_next):
    """
    This middleware intercepts incoming requests and prints the raw body
    for specific POST endpoints that we want to debug.
    """
    if request.method == "POST" and request.url.path in ["/setup/assistant", "/notifications/register-fcm-token"]:
        body_bytes = await request.body()
        
        print("\n" + "="*50)
        print(f"🕵️‍ RAW JSON BODY FOR {request.url.path} 🕵️‍")
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
app.include_router(summaries.router, prefix="/summaries", tags=["Summaries"])
app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
app.include_router(messaging.router, prefix="/messaging", tags=["Messaging"])
app.include_router(history.router, prefix="/history", tags=["History"])

@app.get("/", tags=["Root"])
def read_root():
    """A simple health check endpoint."""
    return {"status": "Orani AI Assistant API is running"}