from pydantic_settings import BaseSettings
from pydantic import AnyUrl, Field

class Settings(BaseSettings):
    TELEGRAM_TOKEN: str = Field(..., description="Bot token from @BotFather")
    BASE_URL: AnyUrl = Field(..., description="Public HTTPS base URL of your service, e.g. https://yourapp.onrender.com")
    WEBHOOK_SECRET: str = Field(..., description="Random secret string for webhook path, e.g. 'whk_9f2b...' ")
    ENV: str = Field(default="production")
    LOG_LEVEL: str = Field(default="INFO")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
