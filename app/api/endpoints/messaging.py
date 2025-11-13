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
from fastapi import Form, File, UploadFile
from typing import Optional, List
import cloudinary
from cloudinary.uploader import upload
from cloudinary.utils import cloudinary_url
from app.config import settings
from datetime import datetime
import logging
logger = logging.getLogger(__name__)
# class SendMessageRequest(BaseModel):
#     user_id: str
#     to_number: str
#     from_number: str
#     body: str

router = APIRouter()

# In app/api/endpoints/messaging.py

@router.post("/send")
async def send_sms_message(
    orani: OraniAIAssistant = Depends(get_orani_assistant),
    # --- START: MODIFIED PARAMETERS ---
    # We now receive data as form fields instead of a JSON payload
    user_id: str = Form(...),
    to_number: str = Form(...),
    from_number: str = Form(...),
    body: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
    # --- END: MODIFIED PARAMETERS ---
):
    """
    [UNIFIED VERSION]
    Sends an SMS or MMS message in a single API call.
    Accepts multipart/form-data with message details and an optional image file.
    """
    try:
        # 1. Validate that there's content to send
        if not body and not file:
            raise HTTPException(status_code=400, detail="Must provide a 'body' or a 'file'.")

        media_url_list = []

        print("Preparing to send message:", {
            "user_id": user_id,
            "to_number": to_number,
            "from_number": from_number,
            "body": body,
            "file": file.filename if file else None
        })

        # 2. If a file is included, upload it to Cloudinary
        if file:
            logger.info("Image file detected. Uploading to Cloudinary...")
            # Configure Cloudinary
            cloudinary.config(
                cloud_name=settings.CLOUDINARY_CLOUD_NAME,
                api_key=settings.CLOUDINARY_API_KEY,
                api_secret=settings.CLOUDINARY_API_SECRET,
                secure=True
            )
            # Upload the file and get the URL
            upload_result = cloudinary.uploader.upload(
                file.file,
                folder=f"mms_attachments/{datetime.now().strftime('%Y-%m')}"
            )
            secure_url = upload_result.get("secure_url")
            if not secure_url:
                raise HTTPException(status_code=500, detail="Cloudinary upload failed.")
            
            media_url_list.append(secure_url)
            logger.info(f"Image uploaded successfully. URL: {secure_url}")

        # 3. Prepare and send the message via Twilio
        client = Client(orani.twilio_account_sid, orani.twilio_auth_token)
        twilio_params = {
            "to": to_number,
            "from_": from_number,
        }
        if body:
            twilio_params["body"] = body
        if media_url_list:
            twilio_params["media_url"] = media_url_list

        twilio_message = client.messages.create(**twilio_params)

        # 4. Save the complete message to our database
        sent_message = Message(
            user_id=user_id,
            message_sid=twilio_message.sid,
            to_number=to_number,
            from_number=from_number,
            body=body,
            media_urls=media_url_list if media_url_list else None,
            direction="outbound"
        )
        with Session(engine) as session:
            session.add(sent_message)
            session.commit()

        return {"status": "success", "message_sid": twilio_message.sid}

    except Exception as e:
        logger.error(f"Failed to send unified SMS/MMS: {str(e)}")
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