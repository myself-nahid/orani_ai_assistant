from app.assistant import OraniAIAssistant
from app.config import settings

orani_assistant = OraniAIAssistant(
    backend_api_base_url=settings.BACKEND_API_BASE_URL,
    vapi_api_key=settings.VAPI_API_KEY,
    twilio_account_sid=settings.TWILIO_ACCOUNT_SID,
    twilio_auth_token=settings.TWILIO_AUTH_TOKEN,
)

def get_orani_assistant() -> OraniAIAssistant:
    """Dependency injector that provides a single instance of the OraniAIAssistant."""
    return orani_assistant