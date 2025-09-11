from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.assistant import OraniAIAssistant
from app.api.deps import get_orani_assistant

router = APIRouter()

class OutboundCallRequest(BaseModel):
    user_id: str
    phone_number_to_call: str

@router.post("/outbound")
def trigger_outbound_call(
    payload: OutboundCallRequest,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """Endpoint to initiate an outbound call from the assistant."""
    call_result = orani.make_outbound_call(
        user_id=payload.user_id,
        phone_number_to_call=payload.phone_number_to_call
    )
    
    if call_result:
        return {"status": "success", "call_details": call_result}
    else:
        raise HTTPException(status_code=500, detail="Failed to initiate outbound call.")