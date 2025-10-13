import logging
from typing import Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException, Response

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
    This is the new entry point for inbound calls from Twilio.
    It tries to ring the user's softphone client first, then forwards to the AI.
    """
    form = await request.form()
    called_number = form.get("To") # The Twilio number that was dialed

    # 1. Find which user this number belongs to
    user_id = orani._get_user_id_from_phone_number(called_number)
    if not user_id:
        # Handle the case where the number isn't assigned to anyone
        return Response("<Response><Hangup/></Response>", media_type="application/xml")

    # 2. Get that user's profile and assistant ID
    profile = orani._get_business_profile(user_id)
    assistant_id = orani._get_assistant_id(user_id)

    if not (profile and assistant_id):
        # Handle the case where the user isn't fully configured
        return Response("<Response><Hangup/></Response>", media_type="application/xml")

    # 3. Calculate the timeout (Ring Count * ~5 seconds per ring is a good estimate)
    timeout = profile.ring_count * 5

    # 4. Construct the Vapi webhook URL for the AI assistant (the fallback)
    vapi_redirect_url = f"https://api.vapi.ai/webhook/twilio?assistantId={assistant_id}"

    # 5. Generate the TwiML response
    # It will try to dial the user's "client" (their softphone) for 'timeout' seconds.
    # If there's no answer, it will execute the <Redirect> verb.
    twiml_response = f"""
    <Response>
        <Dial timeout="{timeout}">
            <Client>{user_id}</Client>
        </Dial>
        <Redirect>{vapi_redirect_url}</Redirect>
    </Response>
    """
    
    return Response(content=twiml_response, media_type="application/xml")