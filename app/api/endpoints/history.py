from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from app.api.schemas import ConversationPreview
from app.assistant import OraniAIAssistant
from app.api.deps import get_orani_assistant

router = APIRouter()

@router.get("/{user_id}/latest", response_model=List[ConversationPreview]) 
def get_latest_history_previews(
    user_id: str,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """
    Retrieves a list of the most recent interactions (previews) for each
    conversation thread. Optimized for building an inbox view.
    """
    preview_data = orani.get_conversation_previews(user_id)
    print("Retrieved conversation previews:", preview_data)
    
    if preview_data and "previews" in preview_data:
        return preview_data["previews"] 
    else:
        raise HTTPException(status_code=404, detail=f"No history found for user {user_id}.")



@router.get("/{user_id}/{customer_number}")
def get_unified_history(
    user_id: str,
    customer_number: Optional[str] = None, 
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """
    Retrieves a combined, chronological history of all calls and messages
    for a given user. If a 'customer_number' query parameter is provided,
    the history is filtered to only include interactions with that customer.
    """
    if customer_number:
        # If a customer number is provided, call the filtering function
        history_data = orani.get_unified_history_for_customer(user_id, customer_number)
    else:
        # Otherwise, get the complete history for the user
        history_data = orani.get_unified_history_for_user(user_id)
    
    if history_data and history_data.get("history"):
        print("Retrieved unified history:", history_data)
        return history_data
    else:
        detail_msg = f"Could not retrieve history for user {user_id}."
        if customer_number:
            detail_msg += f" with customer {customer_number}."
        
        raise HTTPException(status_code=404, detail=detail_msg)