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
    ring_count: Optional[int] = Field(default=4)
    recording_enabled: bool = Field(default=False)

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
    recording_url: Optional[str] = Field(default=None)



# In app/models.py
class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    
    # Twilio's unique ID for the message
    message_sid: str = Field(unique=True, index=True) 
    
    # The 'to' and 'from' numbers
    to_number: str
    from_number: str
    
    # The content of the message
    body: str
    
    # Was it an 'inbound' (customer reply) or 'outbound' (user sent) message?
    direction: str 
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class PhoneNumber(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    phone_number: str = Field(unique=True, index=True) # The number string, e.g., +1888...
    vapi_phone_id: str # The ID from Vapi, e.g., phone_... or a UUID
    is_active: bool = Field(default=False) # Is this the number currently linked to the assistant?