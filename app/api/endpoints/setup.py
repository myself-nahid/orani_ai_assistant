import logging
from fastapi import APIRouter, Depends, HTTPException

from app.assistant import OraniAIAssistant
from app.api.deps import get_orani_assistant

router = APIRouter()
logger = logging.getLogger(__name__)

from app.api.schemas import AssistantDataPayload, PhoneSetupRequest

@router.post("/assistant")
def upsert_assistant(
    payload: AssistantDataPayload,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """
    Creates a new assistant or updates an existing one based on the
    provided business profile data. This is an "upsert" operation.
    """
    try:
        assistant = orani.upsert_assistant_and_profile(payload.model_dump())
        if assistant:
            return {"status": "success", "assistant": assistant}
        else:
            raise HTTPException(status_code=500, detail="Failed to create or update assistant.")
    except Exception as e:
        logger.error(f"Upsert error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error during upsert.")

# @router.post("/phone")
# def setup_phone(
#     payload: PhoneSetupRequest,
#     orani: OraniAIAssistant = Depends(get_orani_assistant)
# ):
#     """
#     Set up and configure a phone number for a user's assistant.
#     """
#     try:
#         phone_setup = orani.setup_phone_number(
#             user_id=payload.user_id,
#             phone_number=payload.phone_number
#         )
#         if phone_setup:
#             return {"status": "success", "phone": phone_setup}
#         else:
#             raise HTTPException(status_code=500, detail="Failed to set up phone")
#     except Exception as e:
#         logger.error(f"Phone setup error: {str(e)}")
#         raise HTTPException(status_code=500, detail="Internal server error")