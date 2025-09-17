from pydantic import BaseModel, Field
from typing import Dict, Any
from typing import List, Optional

class CompanyInfoSchema(BaseModel):
    business_name: str
    website_url: Optional[str] = None
    email: Optional[str] = None
    company_details: Optional[str] = None

class PriceInfoSchema(BaseModel):
    package_name: str
    package_price: str

class BookingLinkSchema(BaseModel):
    booking_title: str
    booking_link: str

class PhoneNumberSchema(BaseModel):
    phone_number: str

class HoursOfOperationSchema(BaseModel):
    days: List[str]  
    start_time: str
    end_time: str

class CallDataSchema(BaseModel):
    call_types: Optional[List[str]] = None
    industries: Optional[List[str]] = None
    work_styles: Optional[List[str]] = None
    assistances: Optional[List[str]] = None

class AssistantDataPayload(BaseModel):
    user_id: str
    company_info: Optional[CompanyInfoSchema] = None
    price_info: List[PriceInfoSchema] = []
    booking_links: List[BookingLinkSchema] = []
    phone_numbers: List[PhoneNumberSchema] = []
    hours_of_operation: List[HoursOfOperationSchema] = []
    call_data: List[CallDataSchema] = []

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