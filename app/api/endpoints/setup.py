import logging
from fastapi import APIRouter, Depends, HTTPException

from app.assistant import OraniAIAssistant
from app.api.deps import get_orani_assistant
from app.api.schemas import AssistantSetupRequest, PhoneSetupRequest

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/assistant")
def setup_assistant(
    payload: AssistantSetupRequest, 
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """Create and configure a new Orani AI assistant for a user."""
    try:
        assistant = orani.create_assistant(
            user_id=payload.user_id,
            # Pass the entire dictionary to create_assistant
            business_info=payload.model_dump() 
        )
        if assistant:
            return {"status": "success", "assistant": assistant}
    except Exception as e:
        logger.error(f"Setup error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/phone")
def setup_phone(
    payload: PhoneSetupRequest,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """
    Set up and configure a phone number for a user's assistant.
    """
    try:
        phone_setup = orani.setup_phone_number(
            user_id=payload.user_id,
            phone_number=payload.phone_number
        )
        if phone_setup:
            return {"status": "success", "phone": phone_setup}
        else:
            raise HTTPException(status_code=500, detail="Failed to set up phone")
    except Exception as e:
        logger.error(f"Phone setup error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")