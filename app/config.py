from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """
    VAPI_API_KEY: str
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    GOOGLE_API_KEY: str
    BACKEND_API_BASE_URL: str

    model_config = SettingsConfigDict(env_file=".env", extra='ignore')

settings = Settings()