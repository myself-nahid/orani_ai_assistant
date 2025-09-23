from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from app.event_stream import broadcaster
import asyncio
import logging

from app.database import engine
from app.models import BusinessProfile
from sqlmodel import Session, select

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/stream")
async def event_stream(request: Request):
    """
    Endpoint for the frontend to connect to and receive real-time notifications via SSE.
    """
    queue = asyncio.Queue()
    await broadcaster.subscribe(queue)
    
    async def event_generator():
        try:
            while True:
                message = await queue.get()
                if await request.is_disconnected():
                    break
                yield message
        finally:
            broadcaster.unsubscribe(queue)

    return EventSourceResponse(event_generator())

class FCMTokenPayload(BaseModel):
    user_id: str
    fcm_token: str

@router.post("/register-fcm-token")
def register_fcm_token(payload: FCMTokenPayload):
    """
    Receives an FCM token from the frontend and saves it to the user's profile in the database.
    """
    with Session(engine) as session:
        statement = select(BusinessProfile).where(BusinessProfile.user_id == payload.user_id)
        profile = session.exec(statement).first()
        
        if profile:
            profile.fcm_token = payload.fcm_token
            session.add(profile)
            session.commit()
            logger.info(f"Updated FCM token for user_id: {payload.user_id}")
            return {"status": "success", "message": "FCM token updated."}
        else:
            raise HTTPException(status_code=404, detail=f"User profile for user_id '{payload.user_id}' not found.")