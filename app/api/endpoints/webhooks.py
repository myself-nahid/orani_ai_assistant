import logging
from typing import Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException

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