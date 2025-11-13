# In app/api/endpoints/messaging.py
from fastapi import APIRouter, Depends, HTTPException, Request
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

router = APIRouter()

@router.post("/send")
async def send_sms_message(
    request: Request,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """
    [UNIFIED VERSION]
    Sends an SMS or MMS message in a single API call.
    Accepts multipart/form-data with message details and an optional image file.
    """
    try:
        # Parse form data manually to handle empty file field
        form = await request.form()
        
        # Extract form fields
        user_id = form.get("user_id")
        to_number = form.get("to_number")
        from_number = form.get("from_number")
        body = form.get("body")
        file = form.get("file")
        
        # Validate required fields
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")
        if not to_number:
            raise HTTPException(status_code=400, detail="to_number is required")
        if not from_number:
            raise HTTPException(status_code=400, detail="from_number is required")
        
        # Normalize file: if it's an empty string or has no filename, set to None
        if file:
            if isinstance(file, str) and file == "":
                file = None
            elif hasattr(file, 'filename') and (not file.filename or file.filename == ""):
                file = None
        
        # 1. Validate that there's content to send
        if not body and not file:
            raise HTTPException(
                status_code=400, 
                detail="Must provide a 'body' or a 'file'."
            )

        media_url_list = []

        logger.info("Preparing to send message: user_id=%s, to=%s, from=%s, body=%s, file=%s",
                    user_id, to_number, from_number, body, 
                    file.filename if (file and hasattr(file, 'filename')) else None)

        # 2. If a file is included, upload it to Cloudinary
        if file and hasattr(file, 'file'):
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
                raise HTTPException(
                    status_code=500, 
                    detail="Cloudinary upload failed."
                )
            
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
        logger.info(f"Message sent successfully. SID: {twilio_message.sid}")

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
            logger.info(f"Message saved to database: {sent_message.message_sid}")

        return {
            "status": "success", 
            "message_sid": twilio_message.sid,
            "media_urls": media_url_list if media_url_list else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send unified SMS/MMS: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to send message: {str(e)}"
        )


@router.get("/{user_id}/{customer_number}")
def get_message_history(
    user_id: str,
    customer_number: str,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """Fetches the message history between a user and a specific customer."""
    try:
        with Session(engine) as session:
            # Query messages where user_id matches and either to or from matches customer
            statement = select(Message).where(
                Message.user_id == user_id
            ).where(
                (Message.to_number == customer_number) | 
                (Message.from_number == customer_number)
            ).order_by(Message.timestamp)
            
            messages = session.exec(statement).all()
            
            logger.info(f"Retrieved {len(messages)} messages for user {user_id} and customer {customer_number}")
            
            return {
                "status": "success",
                "count": len(messages),
                "messages": messages
            }
            
    except Exception as e:
        logger.error(f"Failed to retrieve message history: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve message history: {str(e)}"
        )