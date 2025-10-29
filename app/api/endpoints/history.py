# In the new file: app/api/endpoints/history.py
from fastapi import APIRouter, Depends, HTTPException
from app.assistant import OraniAIAssistant
from app.api.deps import get_orani_assistant
# We don't need the new schemas here because FastAPI will handle it

router = APIRouter()

@router.get("/{user_id}")
def get_unified_history(
    user_id: str,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """
    Retrieves a combined, chronological history of all calls and messages
    for a given user.
    """
    history_data = orani.get_unified_history_for_user(user_id)
    
    if history_data:
        return history_data
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Could not retrieve history for user {user_id}."
        )