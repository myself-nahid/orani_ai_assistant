from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class BusinessInfo(BaseModel):
    business_name: str
    services: str
    availability: str
    booking_link: Optional[str] = None
    greeting: Optional[str] = "Hello! Thank you for calling. How can I help you today?"

class AssistantSetupRequest(BaseModel):
    user_id: str = Field(..., description="The unique identifier for the user.")
    business_info: BusinessInfo

class PhoneSetupRequest(BaseModel):
    user_id: str = Field(..., description="The unique identifier for the user.")
    phone_number: Optional[str] = Field(None, description="Specific phone number to set up. If omitted, an available one will be used.")

class StatusResponse(BaseModel):
    status: str

class SuccessResponse(BaseModel):
    status: str
    data: Dict[str, Any]

class ErrorResponse(BaseModel):
    error: str