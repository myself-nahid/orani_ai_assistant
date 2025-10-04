from typing import List, Optional, Dict, Any
from sqlmodel import Field, SQLModel, JSON, Column
from datetime import datetime

class BusinessProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(unique=True, index=True)
    selected_voice_id: Optional[str] = Field(default=None)
    ai_name: Optional[str] = Field(default="Orani")
    fcm_token: Optional[str] = Field(default=None, index=True)
    profile_data: Dict = Field(sa_column=Column(JSON))

class Assistant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(unique=True, index=True)
    assistant_id: str

class CallSummaryDB(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    call_id: str = Field(index=True)
    user_id: str = Field(index=True) 
    caller_phone: str
    duration: int
    transcript: str
    summary: str
    key_points: List[str] = Field(sa_column=Column(JSON))
    outcome: str
    caller_intent: str
    timestamp: datetime