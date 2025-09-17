from typing import List, Optional
from sqlmodel import Field, SQLModel, JSON, Column
from datetime import datetime

# Table 1: To store the link between a user and their assistant
class Assistant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(unique=True, index=True)
    assistant_id: str

# Table 2: To store the detailed call summaries
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