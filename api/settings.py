# Configuration using pydantic-settings
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PORT: int = 8000
    NEO4J_URL: str = ""
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    IMAGE_TAG: str = "local non docker"
    REDIS_URL: str = "redis://localhost:6379"

    class Config:
        env_file = ".env"

settings = Settings()