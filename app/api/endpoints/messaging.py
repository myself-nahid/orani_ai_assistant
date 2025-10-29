# In app/api/endpoints/messaging.py
from fastapi import APIRouter, Depends, HTTPException
from twilio.rest import Client
# ... other imports ...
from app.models import Message
from app.api.deps import get_orani_assistant
from app.assistant import OraniAIAssistant
from pydantic import BaseModel
from sqlmodel import Session, select
from app.database import engine
from app.api.schemas import SendMessageRequest
import logging
logger = logging.getLogger(__name__)
# class SendMessageRequest(BaseModel):
#     user_id: str
#     to_number: str
#     from_number: str
#     body: str

router = APIRouter()

@router.post("/send")
def send_sms_message(
    payload: SendMessageRequest,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    try:
        client = Client(orani.twilio_account_sid, orani.twilio_auth_token)

        # Send the message via Twilio
        twilio_message = client.messages.create(
            to=payload.to_number,
            from_=payload.from_number,
            body=payload.body
        )

        # Save the sent message to our database
        sent_message = Message(
            user_id=payload.user_id,
            message_sid=twilio_message.sid,
            to_number=payload.to_number,
            from_number=payload.from_number,
            body=payload.body,
            direction="outbound"
        )
        with Session(engine) as session:
            session.add(sent_message)
            session.commit()

        return {"status": "success", "message_sid": twilio_message.sid}

    except Exception as e:
        logger.error(f"Failed to send SMS: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send message.")
    

# In messaging.py

@router.get("/{user_id}/{customer_number}")
def get_message_history(
    user_id: str,
    customer_number: str,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """Fetches the message history between a user and a specific customer."""
    with Session(engine) as session:
        # This is a simplified query; a real one would be more robust
        statement = select(Message).where(Message.user_id == user_id).where(
            (Message.to_number == customer_number) | (Message.from_number == customer_number)
        ).order_by(Message.timestamp)
        
        messages = session.exec(statement).all()
        return messages