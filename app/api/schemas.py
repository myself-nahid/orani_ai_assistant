from pydantic import BaseModel, Field

# In app/api/schemas.py
# Add 'List' to your imports from 'typing'
from typing import Dict, Any, Optional, List

# Define the shape of each nested object

class CompanyInfoSchema(BaseModel):
    business_name: str
    services: Optional[str] = None
    availability: Optional[str] = None
    # Add any other fields that are in CompanyInformationSerializer

class PriceInfoSchema(BaseModel):
    service_name: str
    price: str
    description: Optional[str] = None

class BookingLinkSchema(BaseModel):
    link_name: str
    url: str

class PhoneNumberSchema(BaseModel):
    department: str
    number: str

class HoursOfOperationSchema(BaseModel):
    day_of_week: str # e.g., "Monday", "Saturday - Sunday"
    open_time: str   # e.g., "9:00 AM"
    close_time: str  # e.g., "5:00 PM"

class CallDataSchema(BaseModel):
    # This seems like it might be for call history, not setup.
    # If it's for setup (e.g., knowledge base), we can adjust.
    # For now, let's assume a simple structure.
    question: str
    answer: str

# This is the main request body model
class AssistantSetupRequest(BaseModel):
    user_id: str
    company_info: Optional[CompanyInfoSchema] = None
    price_info: List[PriceInfoSchema] = []
    booking_links: List[BookingLinkSchema] = []
    phone_numbers: List[PhoneNumberSchema] = []
    hours_of_operation: List[HoursOfOperationSchema] = []
    call_data: List[CallDataSchema] = [] # This will act as our knowledge base

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