from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.assistant import OraniAIAssistant
from app.api.deps import get_orani_assistant
from app.api.schemas import CallSummaryResponse 

router = APIRouter()

@router.get("/{user_id}", response_model=List[CallSummaryResponse])
def get_user_summaries(
    user_id: str,
    orani: OraniAIAssistant = Depends(get_orani_assistant)
):
    """
    Retrieves all call summaries for a given user from the local database.
    """
    summaries = orani.get_call_summaries_for_user(user_id)
    
    if summaries is not None:
        return summaries
    else:
        # This will happen if the user_id is not found or an error occurs
        raise HTTPException(
            status_code=404,
            detail=f"Could not retrieve summaries for user {user_id}."
        )