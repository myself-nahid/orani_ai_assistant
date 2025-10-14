import logging
from typing import Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException, Response
from app.firebase_service import send_push_notification
from app.assistant import OraniAIAssistant
from app.api.deps import get_orani_assistant

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/vapi")
async def handle_vapi_webhook(
    request: Request,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """
    Handle all incoming webhooks from Vapi.
    """
    try:
        webhook_data = await request.json()
        logger.info(f"Received webhook: {webhook_data.get('message', {}).get('type')}")
        result = orani.handle_call_webhook(webhook_data)
        return result
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/twilio-inbound")
async def handle_twilio_inbound_call(
    request: Request,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """
    [CORRECT VERSION]
    This is the entry point for calls. It sends a push notification immediately
    and then provides TwiML to ring the user and the AI.
    """
    form = await request.form()
    called_number = form.get("To")
    caller_number = form.get("From")

    user_id = orani._get_user_id_from_phone_number(called_number)
    if not user_id:
        return Response("<Response><Hangup/></Response>", media_type="application/xml")

    # --- THIS IS THE CRUCIAL NOTIFICATION LOGIC ---
    # 1. Get the user's FCM token
    fcm_token = orani._get_fcm_token_for_user(user_id)
    if fcm_token:
        # 2. Send the push notification IMMEDIATELY
        send_push_notification(
            token=fcm_token,
            title="Incoming Call",
            body=f"Call from: {caller_number}",
            data={"callerNumber": caller_number}
        )
    # -----------------------------------------------

    # The rest of the function generates the TwiML as before
    profile = orani._get_business_profile(user_id)
    assistant_id = orani._get_assistant_id(user_id)

    if not (profile and assistant_id):
        return Response("<Response><Hangup/></Response>", media_type="application/xml")

    timeout = profile.ring_count * 5
    vapi_redirect_url = f"https://api.vapi.ai/webhook/twilio?assistantId={assistant_id}"

    twiml_response = f"""
    <Response>
        <Dial timeout="{timeout}"><Client>{user_id}</Client></Dial>
        <Redirect>{vapi_redirect_url}</Redirect>
    </Response>
    """
    return Response(content=twiml_response, media_type="application/xml")