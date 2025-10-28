# In app/api/endpoints/webhooks.py

import logging
from fastapi import APIRouter, Request, Depends, Response
from app.firebase_service import send_push_notification
from app.assistant import OraniAIAssistant
from app.api.deps import get_orani_assistant

router = APIRouter()
logger = logging.getLogger(__name__)

# --- WEBHOOK 1: For VAPI (AI Conversations) ---
@router.post("/vapi")
async def handle_vapi_webhook(
    request: Request,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """Handles all incoming webhooks from Vapi during an AI call."""
    webhook_data = await request.json()
    logger.info(f"Received Vapi webhook: {webhook_data.get('message', {}).get('type')}")
    result = orani.handle_call_webhook(webhook_data)
    return result

# --- WEBHOOK 2: For TWILIO (Initial Call Routing) ---
@router.post("/twilio-inbound")
async def handle_twilio_inbound_call(
    request: Request,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """Receives the initial call from Twilio and provides routing instructions."""
    form = await request.form()
    called_number = form.get("To")
    caller_number = form.get("From")

    user_id = orani._get_user_id_from_phone_number(called_number)
    if not user_id:
        return Response("<Response><Hangup/></Response>", media_type="application/xml")

    # Send the "Incoming Call" push notification
    fcm_token = orani._get_fcm_token_for_user(user_id)

    if fcm_token:
        send_push_notification(token=fcm_token, title="Incoming Call", body=f"Call from: {caller_number}" , data ={"type": "incoming_call", "caller_number": caller_number})

    # Get user settings to generate TwiML
    profile = orani._get_business_profile(user_id)
    assistant_id = orani._get_assistant_id(user_id)

    if not (profile and assistant_id):
        return Response("<Response><Hangup/></Response>", media_type="application/xml")

    timeout = profile.ring_count * 5
    dial_status_handler_url = f"https://e1fa8237ed80.ngrok-free.app/webhook/dial-status?assistantId={assistant_id}"

    twiml_response = f"""
    <Response>
        <Dial timeout="{timeout}" action="{dial_status_handler_url}" method="POST">
            <Client>{user_id}</Client>
        </Dial>
    </Response>
    """
    return Response(content=twiml_response, media_type="application/xml")

# --- WEBHOOK 3: For TWILIO (Dial Status Callback) ---
# In webhooks.py, inside the handle_dial_status function

@router.post("/dial-status")
async def handle_dial_status(request: Request):
    """
    Receives the result of the Dial attempt and redirects to the AI if necessary.
    """
    form = await request.form()
    dial_status = form.get("DialCallStatus")
    assistant_id = request.query_params.get("assistantId")

    logger.info(f"Dial status received: {dial_status} for assistant: {assistant_id}")

    if dial_status in ["no-answer", "busy", "failed", "canceled"]:
        if not assistant_id:
            logger.error("Cannot redirect to AI: assistantId was missing.")
            return Response("<Response><Hangup/></Response>", media_type="application/xml")
        
        # --- THIS IS THE FINAL, CORRECTED URL ---
        vapi_redirect_url = f"https://api.vapi.ai/twilio/call?assistantId={assistant_id}"
        # ------------------------------------------
        
        twiml_response = f"""
        <Response>
            <Redirect>{vapi_redirect_url}</Redirect>
        </Response>
        """
        return Response(content=twiml_response, media_type="application/xml")
    
    return Response("<Response><Hangup/></Response>", media_type="application/xml")