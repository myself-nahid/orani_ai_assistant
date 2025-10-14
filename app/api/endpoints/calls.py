from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.assistant import OraniAIAssistant
from app.api.deps import get_orani_assistant

from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from app.config import settings

router = APIRouter()

# --- THIS IS THE NEW ENDPOINT ---
@router.get("/token")
def get_twilio_token(user_id: str):
    """Generates a Twilio Access Token for the frontend app."""
    try:
        access_token = AccessToken(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_API_KEY_SID,
            settings.TWILIO_API_KEY_SECRET,
            identity=user_id
        )
        voice_grant = VoiceGrant(
            outgoing_application_sid=settings.TWIML_APP_SID,
            incoming_allow=True
        )
        access_token.add_grant(voice_grant)
        jwt_token = access_token.to_jwt()
        return {"token": jwt_token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate Twilio token: {str(e)}")
# ------------------------------

class OutboundCallRequest(BaseModel):
    user_id: str
    from_number: str
    phone_number_to_call: str

@router.post("/outbound")
def trigger_outbound_call(
    payload: OutboundCallRequest,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """Endpoint to initiate an outbound call from the assistant."""
    call_result = orani.make_outbound_call(
        user_id=payload.user_id,
        from_number=payload.from_number, 
        phone_number_to_call=payload.phone_number_to_call
    )
    
    if call_result:
        return {"status": "success", "call_details": call_result}
    else:
        raise HTTPException(status_code=500, detail="Failed to initiate outbound call.")